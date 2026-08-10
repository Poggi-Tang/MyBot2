from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mybot_ui.api import Gateway
from mybot_ui.catalog import build_options
from mybot_ui.chat_engine import parse_listener_event


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live send/self-loop listener smoke test.")
    parser.add_argument("--target", default="AI")
    parser.add_argument("--wait", type=float, default=30)
    parser.add_argument(
        "--expect-event",
        action="store_true",
        help="Fail unless another account sends an inbound message during the wait window.",
    )
    args = parser.parse_args()

    events: list[dict] = []
    gateway = Gateway()
    gateway.add_listener(events.append)
    connected = gateway.connect().result(timeout=10)
    if not connected.ok:
        raise RuntimeError(connected.error)
    account = gateway.clients[0]

    try:
        options = build_options(
            "AddMessageListener",
            {"targets": [args.target], "open": False, "monitor_read_conversations": True},
        )
        listening = gateway.call(account, "AddMessageListener", options).result(timeout=10)
        print("listener:", listening.ok, listening.error)

        time.sleep(2)
        marker = "[LISTENER-VERIFY] \u4e2d\u6587 ping"
        sent = gateway.call(
            account,
            "SendMessage",
            build_options("SendMessage", {"who": args.target, "message": marker}),
        ).result(timeout=40)
        print("send:", sent.ok, repr(sent.value), sent.error)

        deadline = time.time() + args.wait
        while time.time() < deadline and not events:
            time.sleep(0.5)

        print("events:", len(events))
        for event in events[:2]:
            print("raw:", json.dumps(event, ensure_ascii=True)[:5000])
            accepted = parse_listener_event(event.get("data", ""), self_names={account})
            print("accepted:", [message.__dict__ for message in accepted])
        if args.expect_event and not events:
            print("No inbound callback received during the wait window.")
            return 2
        if not events:
            print("No self callback received; outbound messages will not create a reply loop.")
        return 0
    finally:
        gateway.call(account, "PauseMessageListener", "").result(timeout=10)
        gateway.close()


if __name__ == "__main__":
    raise SystemExit(main())
