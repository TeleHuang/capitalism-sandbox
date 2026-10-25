# EcoSim 工作方式（给所有代理/继任者）

## 标准工作流（2026-10 起：JS/TS 唯一逻辑源）

1. **唯一逻辑源：TypeScript/JavaScript**
   - 经济仿真逻辑、UI、测试都在 JS/TS 中维护；按 ES modules/TypeScript
     模块拆分，保持**低耦合、高内聚**，降低认知成本。
   - 迭代用模块化源码 + Node 测试 + 浏览器；发布时用构建脚本把模块、
     CSS、图标、数据内联成**一个自包含 HTML**。
   - 最终 HTML 双击/手机浏览器直接打开；不依赖外部文件、CDN、图片、
     字体或 Python 运行时。
2. **Python 的定位（迁移期 oracle）**
   - `src/ecosim/` 是 V0.6 迁移期的黄金参考/参数校准 oracle，不再接受
     新功能作为最终实现；新机制（A2/人口/银行等）直接以 JS/TS 实现。
   - 用固定 seed 的 Python 黄金运行对照 JS 指标；JS 通过 parity 后，
     Python 冻结，不再维护第二套经济逻辑。
3. **一致性**
   - 不要长期双维护；Python 只补 oracle/验证所需的最小改动。
   - 本地 Python 驾驶舱是临时诊断界面，不是最终产品。

## 测试与性能

- JS/TS：Node 引擎测试 + 浏览器 60/240 月 smoke；测试保持快速，
  长程/百年验证按需单独跑。
- Python 迁移期仍可跑现有快速套件（`python -m unittest discover -s tests -v`，
  默认 60 月以内；`ECOSIM_SLOW_TESTS=1` 跑长程），但只作 oracle。
- 新功能只加 1–3 个真正防回归的测试；不要为每个功能复制 240/600 月测试。
- 注意性能：避免 O(n²) 全量扫描；优先缓存月度快照/增量更新。
- 价格机制改动必须检查**需求信号是否传到 0 级产品**（煤/铁矿石/粮食），
  用下游投资冲击验证，不能只看最终品价格。
- 价格制度默认是 `free`（无成本价格带，仅内部数值夹紧）；
  `band`/`markup_soft` 是显式旧制度，不再作为默认。

## 文档与协作

- 交接页：`docs/HANDOFF.md`；工作流：`docs/WORKSTREAM_V0.5.md`；
  架构契约：`03_架构设计文档.md`；决策：`docs/decisions/`。
- 每完成一个阶段，更新 HANDOFF/工作流和版本树。
- 用户看的中间产品必须有 UI；纯 CLI 只作为调试/验证。
- 不直接改 `main`；feature 在独立 worktree/分支开发，主代理审查、
  跑测试、cherry-pick 到 `v0.4-integration`。
