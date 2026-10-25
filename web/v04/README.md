# V0.6 经济驾驶舱（本地 API 版）

这是 V0.6 引擎的本地诊断 UI，不是生产部署服务。前端不嵌入任何仿真数据；
所有卡片、图表、诊断表都通过同源 `fetch` 读取后端真实运行的 `Engine.stats` 裁剪结果。

V0.5 的“人口与代际”面板（人口金字塔、出生/死亡、抚养比、养老金收支）保持不变。
V0.6 新增：

- **卡通产品图标**：每个商品一条内联 SVG（粮食/煤炭/铁矿石/钢铁/砖头/纺织/
  化肥/机械/建筑/服务 + 通用兜底），用于 KPI、价格与产量小图、诊断表、工厂面板。
- **工厂面板**：点击行业行、价格/产量卡片标题或机制配方行，查看行业配方、
  生产资料来源、2^N 设备阶梯与当前规模；支持按钮、遮罩、Escape 关闭和键盘操作。
- **机制说明**：生产配方链、2^N 设备阶梯、土地/农机、消费/饥饿、人口/养老金，
  全部使用引擎配置与当月真实统计；无外部图表库、字体、图片或 CDN。

## 启动

在仓库根目录运行（脚本会把 `src/` 加入 Python 路径，不需要虚拟环境之外的依赖）：

```bash
python scripts/serve_dashboard.py --port 8765
```

然后打开：

```text
http://127.0.0.1:8765/
```

首次打开默认制度需要约 30–45 秒（240 个月、seed 1）。页面会：

1. 先运行并显示默认的古典制度；
2. 在后台顺序预取凯恩斯与 MMT；
3. 三制度缓存完成后请求 `/api/compare` 填充“三制度对比”表。

缓存只存在于当前 Python 进程内。停止并重启服务后需要重新运行。

## 可选参数

URL 查询参数会原样传给 API：

```text
http://127.0.0.1:8765/?regime=mmt&months=120&seed=7
```

- `regime`: `classical` / `keynesian` / `mmt` / `late_capitalism`
- `months`: 1–1200，默认 240
- `seed`: 整数，默认 1
- `factory`: 启动后直接打开工厂面板，例如 `steel_mill`、`industry:steel_mill`、
  `good:food`（便于分享与截图验证）
- `scroll`: 启动后定位到区块，例如 `mechanism`、`market`、`demography`

启动时可用 `--host` 改监听地址，`--port` 改端口。`--prewarm` 会在启动后
后台跑三制度 240 月；适合先等一段时间再打开页面，不建议在首次页面加载期间使用。

## API

### `GET /api/run`

```text
/api/run?regime=classical&months=240&seed=1
```

返回单次运行的裁剪 JSON：

- `meta`: 月份、seed、制度配置、动态 `goods` / `industries` 元数据；`goods` 含
  `unit`；`industries` 含产出标签；`sectors` 含逐行业配方、设备阶梯、资本品来源、
  `max_firms` 与农业土地/化肥参数；`mechanism` 含土地、饥饿、温饱篮子等全局参数
- `scalars`: 逐月标量序列（存活、失业、GDP、投资、债务、央行货币、银行、预算、利润、
  人口/养老金、土地/农机、粮食救济与饥饿死亡等）
- `goods`: 逐商品序列（价格、产量、需求、供给、成交、库存、价格带、零产出 streak）
- `industries`: 逐月企业数、工人数、活跃项目、名义产能 `capacity`（熟练度 1，
  农业 = 土地 × 亩产）与在产设备台数 `equipment_units`
- `demography`: 年龄桶列表与逐月 `age_histogram`（人口金字塔）；人口/出生/死亡/
  抚养比/养老金等标量在 `scalars`
- `warnings`: 每月引擎告警

### `GET /api/meta`

不运行引擎，返回静态 `goods`、`industries`、`sectors` 和 `mechanism` 元数据。
工厂面板与机制说明也可从 `/api/run` 的 `meta` 读取同一份数据。

### `GET /api/compare`

```text
/api/compare?months=240&seed=1
```

返回三制度轻量逐月摘要、期末摘要、累计死亡、零产出月数和货币守恒检查。
它复用 `/api/run` 的内存缓存；如果三个制度尚未运行，会先运行它们（240 月时
通常约 1–2 分钟）。

### `GET /api/health`

返回服务版本和内存缓存条目数。

## 前端文件

- `index.html`: 页面骨架、机制说明区块、工厂面板容器、错误横幅、加载占位
- `app.js`: API 加载、时间轴/制度切换、内联 SVG 图表、产品图标、工厂面板、机制说明
- `styles.css`: 深色驾驶舱样式、图标/面板/响应式布局

图表与图标全部使用内联 SVG / DOM，不加载 CDN、图表库、外部字体或图片；
新增商品即使没有专属图标，也会显示通用木箱图标与动态标签。

## 验证

```bash
# Python 单测（含 /api/run meta、行业设备阶梯和 node --check app.js）
PYTHONPATH=src python -m unittest discover -s tests -v

# 启动服务后截图（60 月；先访问 /api/run 预热缓存可以让截图更快）
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu \
  --screenshot="$TEMP/ui-cockpit-60.png" --window-size=1440,1200 \
  "http://127.0.0.1:8765/?months=60&seed=1&regime=classical"

# 直接打开工厂面板（也可用 DevTools Protocol 精确截图）
"...chrome.exe" --headless=new --disable-gpu --screenshot="$TEMP/ui-factory-60.png" \
  --window-size=1440,1200 --virtual-time-budget=20000 \
  "http://127.0.0.1:8765/?months=60&seed=1&regime=keynesian&factory=steel_mill"
```

仓库内 `web/screenshots/v06-*.png` 是 V0.6 的 60 月验证截图。
