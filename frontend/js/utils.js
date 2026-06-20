var MS_PER_DAY = 24 * 60 * 60 * 1000;
var DATA_END_DATE = "2026-05-10";
var DATA_MIN_DATE = "2009-01-01";
var WORD_COLORS = ["#1f7a8c", "#bf5b45", "#315f9c", "#6f5c2f", "#2f7d55", "#7b4f86"];
var PARALLEL_COLORS = ["#1f7a8c", "#bf5b45", "#315f9c", "#2f7d55", "#7b4f86", "#8f6a2f", "#3f6f8f", "#9b4d64"];
var PARALLEL_DEFAULT_DIMENSIONS = [
  "viewCount",
  "danmakuCount",
  "durationMinutes",
  "danmakuRate",
  "coinRate",
  "favoriteRate",
  "peakDensity",
  "positiveRatio",
  "lexicalRichness",
];

function toDate(value) {
  return new Date(`${value}T00:00:00`);
}

function toDateString(date) {
  return date.toISOString().slice(0, 10);
}

function eachDate(start, end) {
  const rows = [];
  const startDate = toDate(start);
  const endDate = toDate(end);
  for (let time = startDate.getTime(); time <= endDate.getTime(); time += MS_PER_DAY) {
    rows.push(toDateString(new Date(time)));
  }
  return rows;
}

function bucketKey(dateText, bucket) {
  if (bucket === "day") return dateText;
  const date = toDate(dateText);
  if (bucket === "week") {
    const day = date.getDay() || 7;
    const monday = new Date(date.getTime() - (day - 1) * MS_PER_DAY);
    return toDateString(monday);
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`;
}

function aggregateRows(rows, bucket, fields) {
  if (bucket === "day") {
    return rows.map((row) => ({
      ...row,
      rangeStart: row.date,
      rangeEnd: row.date,
    }));
  }

  const grouped = new Map();
  for (const row of rows) {
    const key = bucketKey(row.date, bucket);
    if (!grouped.has(key)) {
      grouped.set(key, {
        date: key,
        rangeStart: row.date,
        rangeEnd: row.date,
        ...Object.fromEntries(fields.map((field) => [field, 0])),
      });
    }
    const target = grouped.get(key);
    target.rangeEnd = row.date;
    for (const field of fields) {
      target[field] += Number(row[field] || 0);
    }
  }
  return Array.from(grouped.values());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
