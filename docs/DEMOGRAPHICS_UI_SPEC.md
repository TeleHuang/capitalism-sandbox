# 人口/退休金驾驶舱面板规格（V0.5）

> **状态：已实现（D2，`3833c23`）**。`/api/run` 增加 demography 分组，
> `web/v04` 增加人口 KPI、金字塔、出生/死亡、抚养比、养老金收支图；
> 截图见 `web/screenshots/v05-demography-*.png`。以下为原始规格。
>
> 等 `feature/demography` 合并后，由 UI 代理在现有 `web/v04` 上加一块
> “人口与代际”面板。数据必须来自同一份 `Engine.stats`，不得写死。

## 1. 后端 API

`scripts/serve_dashboard.py` 的 `/api/run` 增加 `demography` 分组：

```json
{
  "demography": {
    "population": [...],
    "children": [...],
    "working_age": [...],
    "retirees": [...],
    "labor_force": [...],
    "employed": [...],
    "unemployed": [...],
    "births": [...],
    "deaths": [...],
    "birth_rate": [...],
    "death_rate": [...],
    "dependency_ratio": [...],
    "old_age_dependency": [...],
    "average_age": [...],
    "median_age": [...],
    "age_histogram": { "0-4": [...], "5-9": [...], "...": [...] },
    "pension_revenue": [...],
    "pension_spending": [...],
    "pension_balance": [...],
    "pension_fund": [...]
  }
}
```

- `SCALAR_FIELDS` 或独立 `DEMOGRAPHY_FIELDS` 选择字段；
- `age_histogram` 是“年龄桶 → 逐月序列”；前端按当前 tick 取一项；
- 兼容旧 stats：缺字段时返回 0 或空数组，不崩。

## 2. 前端总览

在现有总览增加一行 4 张 KPI 卡：

1. **人口**：总人口、儿童、劳动年龄、退休；
2. **出生/死亡**：本月出生、死亡、出生率/死亡率；
3. **抚养比**：总抚养比、老年抚养比（retirees/employed）；
4. **养老金**：本月收入/支出/结余、基金余额。

## 3. 图表

- **人口金字塔**：按 5 岁年龄桶，横向条形（男/女可选；先做总人数）；
- **出生/死亡**：双折线，逐月；
- **抚养比**：总抚养比 + 老年抚养比；
- **养老金**：收入/支出柱状 + 基金余额线；
- 时间轴与现有 slider 共用；1200 月可选（服务端 `MAX_MONTHS=1200` 已支持）。

## 4. 详情

新增 `?detail=demography` 领域详情：

- 年龄结构表（桶/人数/占比）；
- 出生/死亡/迁移（暂无迁移）汇总；
- 养老金制度参数（缴费率、替代率、退休年龄）与当月收支；
- 依赖比、平均年龄、中位年龄；
- 剧本说明（classical 无养老金；Keynesian/MMT/晚期资本主义有）。

## 5. 制度对比

`/api/compare` 增加轻量人口摘要：

- 期末人口、儿童/劳动年龄/退休、抚养比、养老金结余/基金；
- 三制度对比表新增“人口/抚养比/养老金”列。

## 6. 验收

- 真实 1200 月运行可打开；时间轴能看人口金字塔随年龄变化；
- 儿童/退休者不被算作失业；失业率分母是劳动年龄劳动人口；
- 养老金收支/基金与 stats 一致；
- 页面无外部资源、无错误横幅；
- 旧面板（GDP/商品/行业/银行/政府）不回归。
