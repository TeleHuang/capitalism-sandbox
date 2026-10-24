"""SessionStart hook：把 docs/HANDOFF.md 注入新会话上下文。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs" / "HANDOFF.md"


def main() -> int:
    try:
        text = HANDOFF.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = "缺少 docs/HANDOFF.md；请先恢复交接文档。"
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
