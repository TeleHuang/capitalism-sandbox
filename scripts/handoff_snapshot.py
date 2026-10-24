"""PreCompact hook：把压缩前的 git 状态机械快照写入 docs/COMPACT_LOG.md。

它不做语义总结；高质量的交接由主代理写入 docs/HANDOFF.md。
"""

from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "docs" / "COMPACT_LOG.md"


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=15,
        )
        return result.stdout.strip()
    except Exception as exc:  # pragma: no cover - 防御性
        return f"(failed: {exc})"


def main() -> int:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    branch = _run(["git", "branch", "--show-current"]) or "(detached)"
    status = _run(["git", "status", "--short"]) or "(clean)"
    unstaged = _run(["git", "diff", "--stat"]) or "(no unstaged diff)"
    staged = _run(["git", "diff", "--cached", "--stat"]) or "(no staged diff)"
    recent = _run(["git", "log", "--oneline", "-5"]) or "(no commits)"

    block = f"""
## 自动快照 {stamp}

- 分支：{branch}

### git status
```
{status}
```

### git diff --stat（未暂存）
```
{unstaged}
```

### git diff --cached --stat（已暂存）
```
{staged}
```

### git log -5
```
{recent}
```
"""
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(block)
    print(f"handoff snapshot -> {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
