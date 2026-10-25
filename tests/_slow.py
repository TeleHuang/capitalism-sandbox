"""慢速集成测试标记。

默认测试只跑单元/短程（60 月以内）；240/600/1200 月与全制度长程放在
``ECOSIM_SLOW_TESTS=1`` 下，避免每次开发都等几分钟。

用法：
  python -m unittest discover -s tests -v                 # 快速
  ECOSIM_SLOW_TESTS=1 python -m unittest discover -s tests -v  # 慢速
"""

from __future__ import annotations

import os
import unittest

SLOW_ENABLED = os.environ.get("ECOSIM_SLOW_TESTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

slow = unittest.skipUnless(
    SLOW_ENABLED,
    "slow integration test; set ECOSIM_SLOW_TESTS=1 to run",
)
