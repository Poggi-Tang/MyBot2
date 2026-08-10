from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mybot_ui.api import Gateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe no-click conversation previews.")
    parser.add_argument("--target", default="AI")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.5)
    args = parser.parse_args()

    gateway = Gateway()
    connected = gateway.connect().result(timeout=10)
    if not connected.ok:
        raise RuntimeError(connected.error)
    account = gateway.clients[0]
    durations: list[float] = []
    target = None
    try:
        for _ in range(args.samples):
            started = time.monotonic()
            result = gateway.call(account, "GetVisibleConversations", "").result(timeout=15)
            durations.append(round(time.monotonic() - started, 3))
            if not result.ok or not isinstance(result.value, list):
                raise RuntimeError(result.error or "Invalid conversation preview response")
            target = next(
                (
                    item
                    for item in result.value
                    if isinstance(item, dict) and item.get("conversation_title") == args.target
                ),
                None,
            )
            time.sleep(args.interval)
    finally:
        gateway.close()

    print("poll_seconds:", durations)
    print("target:", target)
    required = {"conversation_title", "conversation_content", "time", "not_read_numbr"}
    return 0 if isinstance(target, dict) and required.issubset(target) else 2


if __name__ == "__main__":
    raise SystemExit(main())
