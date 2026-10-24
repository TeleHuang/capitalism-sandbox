# HTML 发行版（规划中）

最终发行版 将放在这里：一个可以直接在浏览器运行的静态 HTML 应用，不要求安装 Python。

当前状态：**尚未实现**。技术路线与选项见 [[docs/decisions/0003-html-release.md]]。

计划结构：

```
web/
├─ index.html        # 入口：开始界面、参数配置、沙盒视图
├─ app.js            # 界面、图表、交互
├─ engine.js         # 经济内核（与 Python 参考实现保持逻辑一致）
├─ styles.css
└─ golden/           # Python 导出的固定种子黄金运行样例
```

在 HTML 版本落地前，经济规则以 `src/ecosim/` 和 `tests/` 为准。
