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
| `bfdcfee` | V0.4 版本树文档 |
| `0f3888c` | 冲击验证套件 + 10 个会计不变量测试（cherry-pick 自 `feature/validation`） |
| `fc32005` | 服务业/非正规自雇（cherry-pick 自 `feature/services`，50 tests） |
| `9126504` | 驾驶舱行业标签支持服务业 |
| `f3d4248` | 化肥周转资金/招聘优先/2 台上限（cherry-pick 自 `feature/fertilizer`） |
| `9e6b002` | 服务业加入后调整政府失业比较断言（55 tests） |
| `ed4549a` | 参考价锚定的软 markup 可选预设（cherry-pick 自 `feature/l2-soft`，65 tests） |
| `ac48286` | V0.4.1 驾驶舱最终截图（服务业+化肥） |
| `40e4f68` | V0.4.1 快速冲击验证归档 |
| `93205ff` | 信贷冲击死亡链诊断（食品市场出清但零现金工人买不起） |
| `d2ffbcb` | 计划/熟练度单位修复 + 利润率资本主义部门口径（cherry-pick 自 `feature/plan-skill`，65 tests） |
| `76d1eac` | V0.4.2 驾驶舱/版本/文档更新，标签 `v0.4.2` |
| `6e09300` | V0.5 人口/代际/退休金设计草案 |
| `365aa93` | V0.5 人口/代际/退休金模块（cherry-pick 自 `feature/demography` `263e99f`） |
| `7429a3b` | V0.5.1 救济/养老金/土地/统计修复（cherry-pick 自 `fix/demography-safety` `f797b37`，88 tests） |
| `0e15fad` | V0.5.2 家庭农场所有者剩余索取者记账（cherry-pick 自 `fix/household-farm-income` `035c97f`，95 tests） |
| `3833c23` | V0.5 D2 人口驾驶舱：人口 KPI/金字塔/出生死亡/抚养比/养老金 + API demography |
| `ca5ebeb` | V0.6 UI：产品图标、工厂点按面板、机制说明（cherry-pick 自 `feature/ui-icons` `b350714`） |
| `727c388` | V0.6 B：工资—生产率规则、8h/16h、free 成本加成价格（cherry-pick 自 `feature/v06-wage-price` `9fbcb4d`） |
| `8a9fdd7` | V0.6 A：收入依赖需求、肉类质量阶梯、服务吸收劳动（cherry-pick 自 `feature/v06-demand` `1d3bde4`） |
| `4f15f01` | V0.6 单文件 HTML 发行版：JS 引擎/模块化源码/黄金对比（cherry-pick 自 `feature/html-engine` `0336132`） |

## Feature 分支

| 分支 | 最新提交 | 状态 | 说明 |
|---|---|---|---|
| `feature/ui-cockpit` | `d8cdae7` | 已合并 | 本地 API 驾驶舱（Python http.server + HTML/JS） |
| `feature/ui-comparison` | — | 暂停 | 第二套 UI 方案；worktree 保留 |
| `feature/services` | `79d27de` | 已合并 | 服务业/非正规自雇，古典失业 43%→9.3% |
| `feature/l2` | `62f3217` | 暂停 | 自由 markup/LES 诊断脚本 WIP |
| `feature/l2-soft` | `7c97df0` | 已合并 | 参考价锚定的软 markup（成本加成 + ±15% 走廊，主线 `ed4549a`） |
| `feature/plan-skill` | `ed231e1` | 已合并 | 计划按熟练度调整产能、负利润率修正（主线 `d2ffbcb`） |
| `feature/fertilizer` | `61fae0e` | 已合并 | 化肥周转资金/招聘优先/2 台上限（主线 `f3d4248`） |
| `feature/validation` | `1891485` | 已合并 | 冲击测试、不变量、验证报告（主线 `0f3888c`） |
| `feature/demography` | `263e99f` | 已合并 | V0.5 人口/代际/退休金/晚期资本主义（主线 `365aa93`） |
| `fix/demography-safety` | `f797b37` | 已合并 | 救济缓冲/政府融资/PAYG 代扣/土地继承/测试强化（主线 `7429a3b`） |
| `fix/household-farm-income` | `035c97f` | 已合并 | 自耕农剩余索取者记账/经营所得 payout（主线 `0e15fad`） |
| `feature/price-guidance` | `7c1d949` | 待合并/待组合测试 | opt-in 供求指导价 v1+v2；纯价格仍崩溃，默认 band |
| `feature/v06-demand` | `1d3bde4` | 已合并 | 收入依赖需求/肉类/服务吸收（主线 `8a9fdd7`） |
| `feature/v06-wage-price` | `9fbcb4d` | 已合并 | 工资—生产率/8h/16h/free 价格（主线 `727c388`） |
| `feature/html-engine` | `0336132` | 已合并 | TS/JS 单一逻辑源 + 单文件 HTML 核心发行版（主线 `4f15f01`） |
| `feature/v06-durables` | — | 已取消 | A2 推迟到 JS 发行版之后 |

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
