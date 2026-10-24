# 本地 LLM 经理调试

LLM 经理是**可选**功能，默认仿真不访问网络。API token 只放在本机，不进入 Git。

## 方式一：环境变量

```powershell
$env:ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN = "<你的本地 token>"
$env:ANTHROPIC_MODEL = "deepseek-v4-flash-vision-exp[1M]"
python scripts/llm_probe.py --months 60 --industry fertilizer_factory
```

## 方式二：本地设置文件

```powershell
python scripts/llm_probe.py --settings "%USERPROFILE%\.claude\settings_DS.json" --months 60
```

设置文件的 `env` 段需要包含：

- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_AUTH_TOKEN`
- 可选的 `ANTHROPIC_MODEL`

## 安全规则

- `settings_DS.json`、`.env`、`llm_cache.json` 已加入 `.gitignore`；
- 不要用 `git add -f` 强制提交这些文件；
- 脚本不会打印 token，也不会把 token 写入 `stats` 或运行 JSON；
- 如果 token 已经出现在聊天/日志/提交里，立即在服务商后台轮换。

## 当前能力

`scripts/llm_probe.py` 会先跑一段确定性仿真，再把一家企业的状态和可选的 2^N 设备列表交给模型，要求它返回：

```json
{
  "action": "hold",
  "equipment_key": null,
  "reserve_cash": 300,
  "reason": "一句中文理由"
}
```

它只做**探针**，不会改变仿真。下一步是把通过校验的决策接入 `Engine._investment_decisions`，并保留规则回退。
