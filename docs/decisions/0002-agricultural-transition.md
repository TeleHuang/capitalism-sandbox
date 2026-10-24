# ADR 0002 — Agricultural transition through a land market

- Status: accepted (provisional)
- Date: 2026-10-24
- Context: The previous prototype had 600 self-employed farmers and a tight food
  balance. Industrial goods were produced, but no one founded agricultural enterprises
  or bought farm machinery/fertilizer, so agricultural labour productivity stayed flat.
- Decision:
  1. Land is a fixed 6000-mu asset owned by 600 smallholders (10 mu each).
  2. Smallholders sell whole plots when the land price exceeds their reservation price.
  3. Capitalist farms buy land, hire workers, buy machinery and fertilizer when
     expected ROI exceeds the investment hurdle.
  4. Farm machinery raises land per worker; fertilizer doubles yield per mu.
  5. A sold-out smallholder becomes a landless worker; the buyer's farm can hire them.
- Why: The missing link was not a parameter but a missing market and a missing
  investor. Without land, entry and an input market, agricultural productivity cannot
  respond to food prices.
- Alternatives considered:
  - state-led agricultural investment (rejected for V0.2: no government sector yet);
  - smallholder cooperatives (deferred: needs credit institutions);
  - exogenous productivity growth (rejected: would hide the missing mechanism).
- Consequences:
  - land price and land distribution become observable metrics;
  - the transition is gradual and can produce land-price cycles;
  - the model now needs a proper land/asset valuation in the balance sheet (next step).
