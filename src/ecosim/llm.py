"""可选的 LLM 经理层。

默认不参与仿真；只有显式创建 ``LLMClient`` 并调用时才会访问网络。
API 凭据只从环境变量或本地 JSON 读取，绝不写入仓库、日志或运行统计。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class LLMError(RuntimeError):
    """LLM 调用或输出解析失败。"""


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str = "deepseek-chat"

    @classmethod
    def from_env(cls, model: Optional[str] = None) -> "LLMConfig":
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        if not base_url or not api_key:
            raise LLMError(
                "缺少 ANTHROPIC_BASE_URL 或 ANTHROPIC_AUTH_TOKEN；"
                "请先设置环境变量，或使用 --settings 指向本地设置文件。"
            )
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model or os.environ.get("ANTHROPIC_MODEL", "deepseek-chat"),
        )

    @classmethod
    def from_settings(cls, path: str | Path, model: Optional[str] = None) -> "LLMConfig":
        """从 Claude/DeepSeek 风格的本地设置文件读取 env 段。

        只读取 ``env`` 里的 ANTHROPIC_*；不会打印 token。
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        env = data.get("env", {})
        base_url = str(env.get("ANTHROPIC_BASE_URL", "")).rstrip("/")
        api_key = str(env.get("ANTHROPIC_AUTH_TOKEN", ""))
        if not base_url or not api_key:
            raise LLMError("设置文件里没有 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN")
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model or env.get("ANTHROPIC_MODEL") or data.get("model") or "deepseek-chat",
        )


def extract_json(text: str) -> Dict[str, Any]:
    """从模型输出中提取第一个 JSON 对象。

    允许模型使用 ```json 代码块或前后附加说明；不执行任意代码。
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"模型输出中没有 JSON 对象：{text[:200]}")
        text = text[start : end + 1]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("模型输出的 JSON 顶层必须是对象")
    return value


class LLMClient:
    """Anthropic 兼容的 Messages API 客户端。"""

    def __init__(self, config: LLMConfig, timeout: float = 60.0):
        self.config = config
        self.timeout = timeout

    def complete(self, system: str, prompt: str, max_tokens: int = 600) -> str:
        try:
            import requests
        except ImportError as exc:
            raise LLMError("需要安装 requests：python -m pip install requests") from exc

        response = requests.post(
            self.config.base_url + "/v1/messages",
            headers={
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.config.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            # 不回显请求头，避免 token 泄漏。
            raise LLMError(f"LLM HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        text = "\n".join(parts).strip()
        if not text:
            raise LLMError(
                f"LLM 返回了空文本（stop_reason={data.get('stop_reason')}, "
                f"blocks={[b.get('type') for b in data.get('content', [])]})"
            )
        return text

    def complete_json(
        self, system: str, prompt: str, max_tokens: int = 600
    ) -> Dict[str, Any]:
        return extract_json(self.complete(system, prompt, max_tokens=max_tokens))


MANAGER_SYSTEM_PROMPT = """你是一家资本主义企业的经理。你必须在当前现金流、长期产能和
未来价格之间做权衡，不能把全部现金砸进设备。只输出一个 JSON 对象，不要输出解释性段落。
JSON 字段：
- action: "hold" 或 "invest"
- equipment_key: 若 invest，给出要新增的设备 key；否则为 null
- reserve_cash: 你希望企业保留的最低现金（数字，元）
- reason: 一句中文理由
"""


def build_manager_prompt(snapshot: Dict[str, Any]) -> str:
    return (
        "以下是企业当前状态和市场快照。请做未来 12 个月的设备投资决策。\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=2)
        + "\n请特别考虑：如果 snapshot 里的 unit_cap 不为 null，当前设备数量不能超过它；\n"
        "化肥厂需要持续买煤作为周转资金；如果现金不足，"
        "即使设备回报率很高也不应继续扩产。"
    )
