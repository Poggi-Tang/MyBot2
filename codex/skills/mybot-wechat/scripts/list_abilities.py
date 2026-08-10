from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    path = root / "extensions" / "index.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"abilities": []}
    print(json.dumps(value.get("abilities", []), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
