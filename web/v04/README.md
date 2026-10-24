# V0.4 经济驾驶舱（本地 API 版）

这是 V0.4 引擎的本地诊断 UI，不是生产部署服务。前端不嵌入任何仿真数据；
所有卡片、图表、诊断表都通过同源 `fetch` 读取后端真实运行的 `Engine.stats` 裁剪结果。

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

- `regime`: `classical` / `keynesian` / `mmt`
- `months`: 1–1200，默认 240
- `seed`: 整数，默认 1

启动时可用 `--host` 改监听地址，`--port` 改端口。`--prewarm` 会在启动后
后台跑三制度 240 月；适合先等一段时间再打开页面，不建议在首次页面加载期间使用。

## API

### `GET /api/run`

```text
/api/run?regime=classical&months=240&seed=1
```

返回单次运行的裁剪 JSON：

- `meta`: 月份、seed、制度配置、动态 `goods` / `industries` 元数据
- `scalars`: 逐月标量序列（存活、失业、GDP、投资、债务、央行货币、银行、预算、利润等）
- `goods`: 逐商品序列（价格、产量、需求、供给、成交、库存、价格带、零产出 streak）
- `industries`: 逐月企业数、工人数、活跃项目
- `warnings`: 每月引擎告警

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

- `index.html`: 页面骨架、错误横幅、加载占位；不含仿真数据
- `app.js`: API 加载、时间轴/制度切换、内联 SVG 图表、诊断表
- `styles.css`: 深色驾驶舱样式与响应式布局

图表全部使用内联 SVG / DOM，不加载 CDN、图表库、外部字体或图片。

## 验证

```bash
# Python 单测
PYTHONPATH=src python -m unittest discover -s tests -v

# 启动服务后截图
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu \
  --screenshot="$TEMP/ui-cockpit-240.png" --window-size=1440,900 \
  "http://127.0.0.1:8765/?months=240&seed=1"
```
