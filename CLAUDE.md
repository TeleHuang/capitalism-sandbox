# EcoSim 工作方式（给所有代理/继任者）

## 标准工作流

1. **迭代阶段：Python + 本地 Web UI**
   - 经济逻辑写在 `src/ecosim/`，本地驾驶舱在 `web/v04/` +
     `scripts/serve_dashboard.py`。
   - Python 按文件/模块拆分，保持**低耦合、高内聚**，降低开发时的智力成本；
     JavaScript 也能做到同样的事，当前选 Python 是为了迭代速度和可测试性。
   - 本地 Web UI 是诊断/迭代界面，**不是最终产品**。
2. **发行阶段：单文件 HTML**
   - 最终交付物是**一个 HTML 文件**，包含全部经济仿真逻辑和 UI；
     电脑双击或手机浏览器直接打开，方便传播。
   - 不依赖外部文件、CDN、图片、字体或 Python 运行时。
   - 不要在每次小改动时生成巨大的自包含 HTML；在发行里程碑统一构建/同步。
3. **一致性**
   - Python 是经济逻辑的权威参考；JS 发行版用固定 seed 的黄金运行
     复现关键指标。
   - 新机制先进入 Python + 本地 UI 验证，稳定后再移植/内联到单文件发行版。

## 测试与性能

- 默认 `python -m unittest discover -s tests -v` 只跑快速单元/60 月以内；
  240/600/1200 月长程用 `ECOSIM_SLOW_TESTS=1`（`tests/_slow.py`）。
- 长程验证优先用 `scripts/validate_v05.py`；不要为每个新功能复制一套
  240/600 月测试。
- 新功能只加 1–3 个真正防回归的测试；开发中用定向测试，合并前跑一次
  slow suite，不要每改一行就跑全量。
- 注意性能：避免 O(n²) 全量扫描；优先缓存月度快照/增量更新。
- 价格机制改动必须检查**需求信号是否传到 0 级产品**（煤/铁矿石/粮食），
  用 `tests/test_price_signal.py` 的下游投资冲击验证，不能只看最终品价格。
- 价格制度默认是 `free`（无成本价格带，仅内部数值夹紧）；
  `band`/`markup_soft` 是显式旧制度，不再作为默认。

## 文档与协作

- 交接页：`docs/HANDOFF.md`；工作流：`docs/WORKSTREAM_V0.5.md`；
  架构契约：`03_架构设计文档.md`；决策：`docs/decisions/`。
- 每完成一个阶段，更新 HANDOFF/工作流和版本树。
- 用户看的中间产品必须有 UI；纯 CLI 只作为调试/验证。
- 不直接改 `main`；feature 在独立 worktree/分支开发，主代理审查、
  跑测试、cherry-pick 到 `v0.4-integration`。
