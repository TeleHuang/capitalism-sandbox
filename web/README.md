# HTML 发行版（规划中）

最终发行版只包含一个 HTML 文件：用户下载后在电脑上双击打开，或在手机上用指定浏览器打开，
即可游玩，不要求安装 Python，也不依赖服务器或外部资源。

当前状态：**视觉原型已存在**（hex-map-preview.html），但尚未接入仿真引擎。它使用内联 SVG/JS，可直接双击打开。技术路线与理由见 [[docs/decisions/0003-html-release.md]]。

计划结构：

```
web/
├─ src/
│  ├─ engine.ts      # 经济内核，与 Python 参考实现保持逻辑一致
│  ├─ ui.ts          # 界面、图表、交互
│  └─ styles.css
├─ build.mjs         # 把 TS/CSS/默认场景内联进单个 HTML
├─ hex-map-preview.html  # 当前六边形地图视觉原型
├─ index.html        # 最终发行文件（构建产物）
└─ golden/           # Python 导出的固定随机种子黄金运行样例
```

构建目标：

1. 一个自包含的 `index.html`，不引用本地文件或 CDN；
2. 打开即进入开始界面，可选择剧本和参数；
3. 游戏内显示人口、阶级、物价、产量、利润率、农业劳动生产率等图表；
4. 与 Python 参考实现共享逻辑定义，用 `golden/` 样例做交叉验证。

在 HTML 版本落地前，经济规则以 `src/ecosim/` 和 `tests/` 为准。
