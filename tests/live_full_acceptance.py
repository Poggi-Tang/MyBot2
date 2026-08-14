from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mybot_ui.api import Gateway, GatewayResult
from mybot_ui.catalog import build_options


def result_summary(function: str, result: GatewayResult, elapsed: float) -> dict[str, Any]:
    value = result.value
    error = str(result.error or "")[:240]
    if function == "OpenMoments" and result.ok and value is False:
        error = "WeChat exposed the Moments navigation item but did not open an SNSWindow"
    return {
        "function": function,
        "ok": bool(result.ok and value is not False),
        "seconds": round(elapsed, 3),
        "result_type": type(value).__name__,
        "result_count": len(value) if isinstance(value, (dict, list)) else None,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded MyBot live acceptance probes.")
    parser.add_argument("--target", default="芝士圆子")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--voice", type=Path)
    parser.add_argument("--messaging", action="store_true")
    parser.add_argument("--moments", action="store_true")
    parser.add_argument("--stickers", action="store_true")
    parser.add_argument("--sticker-send", action="store_true")
    parser.add_argument("--voice-send", action="store_true")
    args = parser.parse_args()

    marker = f"[MyBot acceptance {datetime.now().strftime('%Y%m%d-%H%M%S')}]"
    gateway = Gateway()
    connected = gateway.connect().result(timeout=12)
    if not connected.ok:
        print(json.dumps({"function": "Connect", "ok": False, "error": connected.error}, ensure_ascii=False))
        return 2
    account = gateway.clients[0]
    failures = 0
    sticker: dict[str, Any] | None = None

    def run(function: str, arguments: dict[str, Any], timeout: int = 45) -> GatewayResult:
        nonlocal failures, sticker
        started = time.perf_counter()
        try:
            result = gateway.call(
                account,
                function,
                build_options(function, arguments),
                timeout_seconds=timeout,
            ).result(timeout=timeout + 10)
        except Exception as exc:
            result = GatewayResult(False, error=f"{type(exc).__name__}: {exc}")
        summary = result_summary(function, result, time.perf_counter() - started)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if not summary["ok"]:
            failures += 1
        if function == "ScanAllStickers" and isinstance(result.value, (dict, list)):
            items = (
                result.value.get("Items") or result.value.get("items") or []
                if isinstance(result.value, dict)
                else result.value
            )
            sticker = next((item for item in items if isinstance(item, dict)), None)
        return result

    try:
        for function, arguments, timeout in (
            ("Focus", {}, 30),
            ("GetOwerInfo", {}, 30),
            ("GetVisibleConversations", {}, 30),
            ("GetAllConversations", {}, 90),
            ("GetAllFriendNames", {}, 90),
            ("SearchFriend", {"who": args.target}, 45),
            ("GetTitle", {}, 30),
            ("GetHandler", {}, 30),
            ("GetProcessId", {}, 30),
            ("GetVisibleConversationTitles", {}, 30),
        ):
            run(function, arguments, timeout)

        if args.stickers or args.messaging or args.sticker_send:
            run("SearchFriend", {"who": args.target}, 45)
            run("ScanAllStickers", {}, 180)

        if args.sticker_send:
            if sticker:
                run("SendSticker", {
                    "who": args.target,
                    "category": str(sticker.get("Category") or sticker.get("category") or ""),
                    "sticker": str(
                        sticker.get("Name") or sticker.get("name")
                        or sticker.get("Hash") or sticker.get("hash") or ""
                    ),
                }, 60)
            else:
                failures += 1
                print(json.dumps({"function": "SendSticker", "ok": False, "error": "No scanned sticker item"}, ensure_ascii=False))

        if args.voice_send:
            if args.voice is None or not args.voice.is_file():
                raise ValueError("--voice-send requires an existing --voice")
            run("SendVoiceMessage", {"who": args.target, "file_path": str(args.voice)}, 120)

        if args.messaging:
            if args.file is None or not args.file.is_file():
                raise ValueError("--messaging requires an existing --file")
            run("SendMessage", {"who": args.target, "message": marker + " 文本发送测试"})
            run("SendEmoji", {"who": args.target, "emoji": "微笑"})
            run("SendFile", {"who": args.target, "files": [str(args.file)]}, 60)
            run("SetTopMost", {"who": args.target, "setting": True})
            run("SetTopMost", {"who": args.target, "setting": False})
            run("SetDoNotDisturb", {"who": args.target, "setting": True})
            run("SetDoNotDisturb", {"who": args.target, "setting": False})
            if sticker:
                run("SendSticker", {
                    "who": args.target,
                    "category": str(sticker.get("Category") or sticker.get("category") or ""),
                    "sticker": str(
                        sticker.get("Name") or sticker.get("name")
                        or sticker.get("VisualHash") or sticker.get("visualHash") or ""
                    ),
                }, 60)
            else:
                failures += 1
                print(json.dumps({"function": "SendSticker", "ok": False, "error": "No scanned sticker item"}, ensure_ascii=False))
            if args.voice is not None:
                if not args.voice.is_file():
                    raise ValueError("--voice does not exist")
                run("SendVoiceMessage", {"who": args.target, "file_path": str(args.voice)}, 120)

        if args.moments:
            if args.file is None or not args.file.is_file():
                raise ValueError("--moments requires an existing --file")
            opened = run("OpenMoments", {}, 45)
            if not opened.ok or opened.value is False:
                print(json.dumps({
                    "function": "AddMoments",
                    "ok": False,
                    "error": "OpenMoments failed; publish skipped to preserve cleanup safety",
                }, ensure_ascii=False))
                return 1
            published = run("AddMoments", {"content": marker, "images": [str(args.file)]}, 120)
            if published.ok and published.value is not False:
                run("RemoveMoments", {"content": marker}, 120)
            run("CloseMoments", {}, 30)
    finally:
        gateway.close()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
