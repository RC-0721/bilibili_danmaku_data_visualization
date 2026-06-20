"""Bilibili historical danmaku HTTP client and protobuf parser."""

import json
import time
import zlib
from datetime import datetime

import brotli
import requests
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError

from app.config import HEADERS

try:
    from app.bilibili import dm_pb2
except ImportError:
    raise ImportError("请先编译 app/bilibili/dm.proto：protoc --python_out=app/bilibili app/bilibili/dm.proto")

RATE_LIMIT_COOLDOWN_SECONDS = 5000


class DanmakuResponseError(RuntimeError):
    """弹幕接口异常基类。
    Base exception for danmaku API response errors.
    """

    def __init__(self, message: str, code=None):
        super().__init__(message)
        self.code = code


def decompress(data: bytes) -> bytes:
    try:
        return brotli.decompress(data)
    except Exception:
        try:
            return zlib.decompress(data)
        except Exception:
            pass
    return data


def response_preview(raw: bytes, limit: int = 160) -> str:
    head = raw[:limit]
    text = head.decode("utf-8", errors="replace").replace("\n", "\\n").replace("\r", "\\r")
    hex_head = head[:32].hex(" ")
    return f"text={text!r}, hex={hex_head}"


def fetch_protobuf_danmaku(cid: int, date_str: str) -> bytes:
    url = "https://api.bilibili.com/x/v2/dm/web/history/seg.so"
    params = {"type": 1, "oid": cid, "date": date_str}

    while True:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
        resp.raise_for_status()
        raw = decompress(resp.content)
        stripped = raw.lstrip(b" \t\r")

        if not stripped:
            return b""

        if stripped[:1] in (b"{", b"["):
            try:
                payload = json.loads(stripped.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                raise DanmakuResponseError(f"B站返回JSON样式内容但解析失败: {response_preview(raw)}")

            code = payload.get("code")
            message = payload.get("message") or payload.get("msg") or payload
            if code == -702:
                print(f"  {date_str}:  触发限流(-702)，固定冷却 {RATE_LIMIT_COOLDOWN_SECONDS} 秒后继续重试")
                time.sleep(RATE_LIMIT_COOLDOWN_SECONDS)
                continue
            raise DanmakuResponseError(f"B站返回JSON而不是protobuf: code={code}, message={message}", code=code)

        lower_probe = stripped[:32].lower()
        if lower_probe.startswith((b"<!doctype", b"<html", b"<?xml")):
            raise DanmakuResponseError(f"B站返回HTML/XML而不是protobuf: {response_preview(raw)}")

        return raw


def parse_danmaku(raw: bytes) -> list:
    dm_seg = dm_pb2.DmSegMobileReply()
    try:
        dm_seg.ParseFromString(raw)
    except DecodeError as exc:
        raise DanmakuResponseError(f"protobuf解析失败，响应前缀: {response_preview(raw)}") from exc
    return MessageToDict(dm_seg, preserving_proto_field_name=True).get("elems", [])


def timestamp_to_datetime(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return None
