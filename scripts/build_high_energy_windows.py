"""CLI wrapper for rule-based high-energy window scoring."""

import _bootstrap  # noqa: F401

from app.analysis.high_energy_builder import main


if __name__ == "__main__":
    main()
