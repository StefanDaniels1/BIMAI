"""The `bimai` command. Hook calls (session log, voice, daily nap check) run on every turn, so they load only
what they need; everything else goes to the full CLI."""
from __future__ import annotations

import sys


def main() -> int:
    args = sys.argv[1:]
    if args[:2] == ["log", "hook"]:
        seat = args[args.index("--seat") + 1] if "--seat" in args[:-1] else "me"
        try:
            import json
            from bimai import sessionlog
            sessionlog.handle(json.loads(sys.stdin.read() or "{}"), seat)
        except Exception:
            pass                                 # never fail or print: Claude carries on regardless
        return 0
    if args[:2] == ["voice", "hook"]:
        from bimai import voice
        return voice.hook(sys.stdin.read())
    from bimai.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
