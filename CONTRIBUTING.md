# 贡献与开发流程

## 所有权

| 产物 | 所有者 | 规则 |
|---|---|---|
| `02_需求定义文档.md` | 人 | Code Bot 只提案，不静默修改。 |
| `03_架构设计文档.md` | Code Bot | 必须描述 `src/ecosim/` 里实际存在的机制。 |
| `src/`、`tests/` | Code Bot | 代码改动必须同步更新架构文档。 |
| `docs/REQUIREMENTS_REVIEW.md` | Code Bot | 记录需求冲突和选项。 |
| `04_开发日志文档.md` | Code Bot | 每个里程碑追加一条简短记录。 |
| `web/` | Code Bot | HTML 发行版；当前规划中。 |

## 循环

1. 阅读 `02_需求定义文档.md`。如果某个机制没有写清楚，先在架构文档里设计它。
2. 如果需求在经济/史实上不合理，或内部矛盾：
   - 在 `docs/REQUIREMENTS_REVIEW.md` 增加一条；
   - 给出 2–4 个具体选项，并标明推荐项；
   - 在人做出选择之前，**不要**修改 `02_需求定义文档.md`。
3. 在 `src/ecosim/` 实现选定的设计。
4. 在 `tests/` 增加或更新确定性回归测试。
5. 在同一个变更里更新 `03_架构设计文档.md`。
6. 在 `04_开发日志文档.md` 追加一行。
7. 运行：
   ```powershell
   $env:PYTHONPATH = "src"
   # 默认快速套件：只跑单元/60 月以内；开发循环用这个
   python -m unittest discover -s tests -v
   # 慢速长程（240/600/1200 月）在合并前跑一次
   $env:ECOSIM_SLOW_TESTS = "1"
   python -m unittest discover -s tests -v
   python -m ecosim --months 240 --seed 1
   ```

   长程验证优先用 `scripts/validate_v05.py`，不要给每个新功能再复制一套
   240/600 月集成测试；默认套件保持 <2 分钟。只有真正需要防止回归的
   长程场景才加 `@slow`，并在合并前跑一次。

## 完成标准

- [ ] 快速套件 `python -m unittest discover -s tests -v` 通过。
- [ ] 合并前跑一次慢速套件 `ECOSIM_SLOW_TESTS=1 python -m unittest discover -s tests -v`，
      或至少跑相关的 `@slow` 用例 + `scripts/validate_v05.py`。
- [ ] 固定随机种子下 240 个月运行完成，无异常。
- [ ] 货币总量守恒（审计误差小于 0.01）。
- [ ] 除非场景刻意不启用，核心行业不出现连续 3 个月零产出。
- [ ] 架构文档写明了代码里存在的模块、公式和决策。
- [ ] 需求冲突已记录并给出选项，而不是藏在代码里。
- [ ] 文档和代码注释使用中文。

## 标准工作流：Python 迭代 → 单文件 HTML 发行

这是项目的硬约定，所有代理/继任者都要遵守：

1. **迭代阶段：Python + 本地 Web UI**
   - 经济逻辑在 `src/ecosim/`，驾驶舱在 `web/v04/` +
     `scripts/serve_dashboard.py`。
   - Python 按文件/模块拆分，保持低耦合、高内聚，降低开发智力成本；
     JavaScript 也能实现类似结构，当前选 Python 是为了迭代速度和可测试性。
   - 本地 Web UI 是诊断/预览界面，不是最终产品。
2. **发行阶段：单文件 HTML**
   - 最终产品是**一个 HTML 文件**，包含全部经济仿真逻辑和 UI，
     电脑双击/手机浏览器直接打开即可游玩，方便传播。
   - 不依赖外部文件、CDN、图片、字体或 Python 运行时。
   - 不要在每次小改动时构建巨大的自包含 HTML；在发行里程碑统一构建/同步。
3. **一致性**
   - Python 是经济逻辑的权威参考；HTML/JS 发行版用固定 seed 的黄金运行
     复现关键指标。
   - 新机制先进入 Python + 本地 UI 验证，稳定后再移植/内联到单文件发行版。
   - 矿类等机制文案在 Python config、驾驶舱、单文件发行版三处保持同步。
