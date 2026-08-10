#!/usr/bin/env python3
"""Normalize repeated whitespace in a UTF-8 text file."""

import argparse
import re
import sys
from pathlib import Path


def normalize(text: str) -> str:
    """Collapse every run of whitespace and trim the result."""
    return re.sub(r"\s+", " ", text).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collapse repeated whitespace in a UTF-8 text file."
    )
    parser.add_argument("--input", required=True, type=Path, help="input UTF-8 text file")
    parser.add_argument("--output", required=True, type=Path, help="output text file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = args.input.read_text(encoding="utf-8")
        normalized = normalize(text)
        args.output.write_text(normalized, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"normalized whitespace: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
