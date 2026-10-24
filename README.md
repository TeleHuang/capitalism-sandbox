# Capitalism Sandbox

**资本主义经济模拟 / An agent-based sandbox of a closed capitalist economy.**

A deterministic, monthly-step simulation of a closed economy: rule-driven workers, profit-seeking
capitalists, a spot market, a labour market, a land market, and an investment/entry process. The
long-term goal is to use LLM agents for managers and directors; the current milestone is to make the
rule-based economy structurally sound first.

> Status: **V0.2.0 — refactored core, not yet feature-complete.** The engine runs, is deterministic
> with a fixed seed, and has regression tests. LLM agents, contracts, futures orders, and the full
> dashboard are intentionally deferred.

## Quick start

```powershell
python -m pip install -e .
python -m ecosim --months 240 --seed 1
```

Or without installing:

```powershell
$env:PYTHONPATH = "src"
python -m ecosim --months 240 --seed 1
```

Write a machine-readable run:

```powershell
python -m ecosim --months 240 --seed 1 --json artifacts/run.json
```

Run tests:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## What is implemented in V0.2

- 240 monthly ticks, deterministic RNG, money-conservation audit.
- 9 sectors: agriculture, coal, iron ore, steel, brick, textile, machinery, construction, fertilizer.
- Enterprise-level production with an explicit equipment catalogue, labour requirements and input
  coefficients.
- Flexible reference-price tatonnement; orders are matched highest-bid/lowest-ask at the average
  price. Cost-based guard rails keep a thin market from ratcheting to 10x replacement cost.
- Labour market with actual wage payments, hiring/firing, voluntary hours (16/12/8), skill growth
  and unemployment.
- Capitalist entry and investment based on expected return on capital, with a construction lag.
- **Land market and capitalist agriculture.** Land is scarce and owned by smallholders; farms can
  buy land, hire workers, buy fertilizer and farm machinery. This is the mechanism that allows
  agricultural labour productivity to rise instead of freezing at a subsistence equilibrium.
- Bank liquidity loans, enterprise cash separated from owner cash, dividends, bankruptcy.
- Metrics: GDP, investment, unemployment, aggregate profit rate, capital stock, agricultural
  labour productivity, enterprise counts, living-standard distribution.
- Architecture document kept in sync with the code: [`03_架构设计文档.md`](03_架构设计文档.md).

## What is not implemented yet

- LLM manager/director agents and management hierarchy.
- Contracts, futures/order production, multi-month input smoothing.
- Full UI (the current entry point is a CLI).
- Scenario 0 (iron age) and scenario 2 (late capitalism).
- Multiple capital-good types; V0.2 uses one generic `MACHINERY` good plus `BRICK`/`STEEL` for
  specific equipment.

## Repository layout

```
.
├─ 01_产品介绍文档.md
├─ 02_需求定义文档.md          # owned by the human
├─ 03_架构设计文档.md          # owned by the Code Bot, must match the code
├─ 04_开发日志文档.md
├─ src/ecosim/                 # simulation package
├─ tests/                      # deterministic regression tests
├─ docs/
│  ├─ REQUIREMENTS_REVIEW.md   # conflicts / open questions / options for the human
│  └─ decisions/               # architecture decision records
└─ scripts/
```

## Development workflow

This repository follows a two-owner workflow:

1. **Human owns the requirements document** (`02_需求定义文档.md`). The Code Bot does not silently
   rewrite requirements.
2. **Code Bot owns the architecture document and the code.** Architecture must specify the concrete
   mechanisms that the requirements leave open, and must stay consistent with `src/ecosim/`.
3. When a requirement is economically or historically implausible, or logically inconsistent, the
   Code Bot records the conflict in [`docs/REQUIREMENTS_REVIEW.md`](docs/REQUIREMENTS_REVIEW.md)
   and proposes several options. The human decides; only then is the requirement changed.
4. A change is done only when code, tests, architecture document, and changelog agree.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the detailed checklist.

## License

No license has been chosen yet. Until one is added, all rights are reserved by the author.
