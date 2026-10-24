# V0.4 交接（会话入口）

> 这是每次会话开始时自动加载的一页交接。详细档案见
> `docs/WORKSTREAM_V0.4.md`；设计与决策见
> `docs/decisions/0004-historical-regimes.md`；代码契约见
> `03_架构设计文档.md` 第 18 节。

## 当前基线

- 分支：`v0.4-integration`
- 最新提交：`93205ff`（服务业 + 验证套件 + 化肥修复 + 软 markup + 驾驶舱 + 信贷诊断）
- Python 版本：0.4.0
- 测试：65 个全绿（33 原有 + 10 不变量 + 7 服务业 + 5 化肥 + 10 软 markup）
- UI：`python scripts/serve_dashboard.py --port 8765` → `http://127.0.0.1:8765`
- 已实现：会计修正、L1 生产—库存—订单、L3 投资/手工 t0/替换投资、
  L5 工资曲线/精确用工/跳槽修正、粮食平准库存、银行存款中介、
  classical / keynesian / mmt 三种制度、CLI `--regime`、制度对比脚本。

## 当前 240 月结果（seed=1）

| 制度 | 存活 | 失业率 | GDP | 投资 | 利润率 | 债务 | 央行货币 | 服务业企业 | 化肥首次 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| classical | 1100 | 9.6% | 17,440 | 420 | -0.27% | 0 | 0 | 338 | T20 |
| keynesian | 1100 | 4.6% | 29,908 | 0 | -0.44% | 3,970 | 0 | 311 | T18 |
| mmt | 1100 | 0.0% | 28,915 | 240 | -0.44% | 887,518 | 887,518 | 249 | T18 |

三制度 240 月均 0 死亡；核心行业零产出月数 0–5；化肥投产后连续供应。

## 下一步优先级

1. **UI（已完成）**：本地前后端分离驾驶舱已合并；后续可按用户反馈加图表/钻取。
2. **服务业（已完成）**：古典失业 43%→9.6%，Keynesian 16.9%→4.6%；下一步校准
   服务价格路径和自雇进入/退出。
3. **信贷冲击死亡链（新的最高优先）**：`docs/CREDIT_SHOCK_DIAGNOSIS.md` 已定位：
   粮食市场几乎完全出清（未成交 0.02–0.05 吨），但零现金工人数量≈饥饿人数；
   信贷冻结→企业工资账单无法融资→按比例欠薪→部分工人 0 现金买不起食品。
   下一步：最后贷款人/贴现窗口、wage_arrears 显性化、食品券/定向分配、
   银行冻结规则校准；这些比继续调农业产能更关键。
4. **L2 价格（已有可选版）**：`price_regime="markup_soft"` 已合并（参考价锚定
   ±15% 软走廊 + 库存 markup），默认仍是 band；240 月古典 GDP 17,440→25,136、
   利润率 -0.27%→-0.08%，但资本存量低约 14%。自由 markup/LES 仍是实验分支。
5. **化肥物流（已完成）**：首次使用 T18/T20，投产后连续供应；65 测试。
6. **验证套件（已刷新）**：冲击/不变量脚本已合并；下一步 20–100 seeds、
   冲击起点集成、服务业加入后的完整冲击矩阵。
7. **HTML 单文件发行版**：本地驾驶舱已可用；单文件发行版仍需同步 V0.4。

## 并行版本树（进行中）

基线：`506d92e`（v0.4-integration）。每个 feature 一个 worktree/分支：

| 分支 | worktree | 状态/目标 |
|---|---|---|
| `feature/ui-cockpit` | `.claude/worktrees/ui-cockpit` | **已合并** `d8cdae7`：前后端分离 UI（Python http.server + HTML/JS，localhost） |
| `feature/ui-comparison` | `.claude/worktrees/ui-comparison` | 暂停（减少 CPU/风扇） |
| `feature/services` | `.claude/worktrees/services` | **已合并** `79d27de`：服务业/非正规自雇，古典失业 43%→9.3% |
| `feature/l2` | `.claude/worktrees/l2` | 暂停（减少 CPU/风扇），worktree 保留 |
| `feature/fertilizer` | `.claude/worktrees/fertilizer` | 暂停（减少 CPU/风扇），worktree 保留 |
| `feature/validation` | `.claude/worktrees/validation` | **进行中**：冲击测试、不变量、验证报告 |

集成规则：子代理在各自 worktree 提交；主代理审查 diff、跑测试、按
services → validation → UI 的顺序 cherry-pick 到 `v0.4-integration`；
暂停的 l2/fertilizer 等机器空闲/用户确认后再续。冲突时以测试和用户可见指标为准。

**UI 方向（用户确认）**：前后端分离，不为每个版本生成巨大自包含 HTML。
`scripts/serve_dashboard.py` 用 Python 标准库 `http.server` 提供
`/api/run` 和 `/api/compare`；`web/v04/index.html` + `app.js` 通过 fetch 渲染。
启动后浏览器打开 `http://127.0.0.1:8765`。这也更省 token/内存。

## 工作方式

- 长任务用子代理 + git worktree 并行开发；每个 feature 一个分支/提交。
- 主代理负责方案选型、审查、跑测试、cherry-pick 到 `v0.4-integration`。
- 不直接改 `main`；不提交 API key/本地设置/临时产物。
- 每完成一个阶段，更新本文件和 `docs/WORKSTREAM_V0.4.md`。
- 用户看的中间产品必须有 UI；纯 CLI 只作为调试/验证。

## 常用命令

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m ecosim --months 240 --seed 1 --regime classical
python -m ecosim --months 240 --seed 1 --regime keynesian
python -m ecosim --months 240 --seed 1 --regime mmt
python scripts/compare_regimes.py --months 240 --seed 1 --json artifacts/regimes_240.json
```

## 关键文件

- `src/ecosim/engine.py`：月度主循环、L1 计划、政府结算、银行中介
- `src/ecosim/government.py`：制度/政府/央行/就业保障数据结构
- `src/ecosim/scenarios.py`：`ScenarioConfig` 与三种历史阶段预设
- `src/ecosim/models.py`：AssetPool / FoodReserve / Bank deposits
- `tests/test_feedback.py`、`tests/test_government.py`：新机制回归
- `scripts/compare_regimes.py`：制度对比
- `docs/WORKSTREAM_V0.4.md`：完整进度与剩余问题
