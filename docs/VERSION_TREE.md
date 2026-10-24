# V0.4 版本树

> 基线：`v0.4-integration`。每个 feature 在独立 git worktree/分支开发；
> 主代理审查、跑测试后 cherry-pick。暂停的分支保留 worktree 和 WIP 提交。

## 集成主线

| 提交 | 内容 |
|---|---|
| `9fc7117` | V0.4 负反馈修复、历史阶段与政府/MMT 模块（33 tests） |
| `c3b71f6` | 自动交接文档与会话 hooks 辅助脚本 |
| `506d92e` | stats 增加利润分解/库存/价格带诊断字段 |
| `7926334` | 前后端分离 V0.4 驾驶舱（cherry-pick 自 `feature/ui-cockpit`） |
| `7ea7a35` | 交接文档记录驾驶舱合并与版本树 |

## Feature 分支

| 分支 | 最新提交 | 状态 | 说明 |
|---|---|---|---|
| `feature/ui-cockpit` | `d8cdae7` | 已合并 | 本地 API 驾驶舱（Python http.server + HTML/JS） |
| `feature/ui-comparison` | — | 暂停 | 第二套 UI 方案；worktree 保留 |
| `feature/services` | 进行中 | 进行中 | 服务业/非正规部门，降低古典失业 |
| `feature/l2` | `62f3217` | 暂停 | markup/LES 诊断脚本 WIP |
| `feature/fertilizer` | `91e227e` | 暂停 | 化肥周转资金/供应修复 WIP |
| `feature/validation` | 进行中 | 进行中 | 冲击测试、不变量、验证报告 |

## UI 启动

```powershell
python scripts/serve_dashboard.py --port 8765
# 浏览器打开 http://127.0.0.1:8765
```

## 集成顺序

1. `feature/services`（结构变更，先合）
2. `feature/validation`（脚本/测试/报告）
3. 重新跑 33+ 测试 + 三制度 240 月对比
4. 用集成后的 stats 重新验证驾驶舱（动态 goods/industries keys）
5. 视机器负载恢复 `feature/l2` / `feature/fertilizer` / `feature/ui-comparison`

## 回滚

- 每个 feature 分支可独立 `git revert` 或丢弃；
- 集成主线保留每个 cherry-pick 的提交，便于定位回归；
- 暂停分支的 WIP 提交不进入主线，只作实验记录。
