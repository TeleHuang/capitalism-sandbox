# V0.4 交接（会话入口）

> 这是每次会话开始时自动加载的一页交接。详细档案见
> `docs/WORKSTREAM_V0.4.md`；设计与决策见
> `docs/decisions/0004-historical-regimes.md`；代码契约见
> `03_架构设计文档.md` 第 18 节。

## 当前基线

- 分支：`v0.4-integration`
- 基线提交：`9fc7117`（V0.4 负反馈修复、历史阶段与政府/MMT 模块）
- Python 版本：0.4.0
- 测试：33 个全绿（`tests/`）
- 已实现：会计修正、L1 生产—库存—订单、L3 投资/手工 t0/替换投资、
  L5 工资曲线/精确用工/跳槽修正、粮食平准库存、银行存款中介、
  classical / keynesian / mmt 三种制度、CLI `--regime`、制度对比脚本。

## 当前 240 月结果（seed=1）

| 制度 | 存活 | 失业率 | GDP | 投资 | 利润率 | 债务 | 央行货币 |
|---|---:|---:|---:|---:|---:|---:|---:|
| classical | 1098 | 43.2% | 12,563 | 0 | -0.08% | 0 | 0 |
| keynesian | 1100 | 16.9% | 17,467 | 0 | -0.20% | 746,244 | 0 |
| mmt | 1100 | 0.0% | 15,257 | 706 | -0.01% | 4,188,688 | 4,188,688 |

核心行业零产出：钢/砖/机械 0 个月；纺织 0–4；建筑 3–5。

## 下一步优先级

1. **UI（最高优先级）**：给用户一个能直接看的 V0.4 仪表盘（静态 HTML 或本地服务）。
   必须展示：三制度对比、时间轴、GDP/投资/利润/失业、政府预算/债务、
   央行货币、就业保障、粮食储备、行业产量与零产出、项目队列、银行资产负债表。
2. **服务业/非正规部门**：降低古典 43% 的失业率；9 行业模型缺少劳动吸收部门。
3. **L2 成本加成 + LES**：目前 `price_regime="markup"` / `demand_regime="les"`
   仍是实验分支，固定篮子 + 价格带是默认；需要重新校准 gamma/beta/预算。
4. **化肥物流**：首次使用已提前到 T20/T36，但仍偏晚；需要周转资金/价格校准。
5. **验证套件**：冲击—恢复、20 seeds、典型事实；当前模型接近确定性。
6. **HTML 单文件发行版**：Python 稳定后同步 `web/engine-preview.html`。

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
