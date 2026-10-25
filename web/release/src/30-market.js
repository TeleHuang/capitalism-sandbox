/*
 * EcoSim V0.6 · engine source — module 30: bilateral market, reference-price
 * discovery and the free cost-plus regime path.
 */
import {
  C, GOODS, INITIAL_PRICES, sectorUsesInput,
} from "./00-core.js";
import {
  Enterprise, FoodReserve, InvestmentProject, Worker, Capitalist,
} from "./10-models.js";
import { Government } from "./15-government.js";

class Market {
  constructor(prices) {
    this.referencePrices = { ...prices };
    this.priceRegime = "band";
    this.costAnchors = {};
    this.markupAnchors = {};
    // Optional explicit anchors (used by A2 scrap: p_scrap tracks iron ore).
    this.priceAnchors = {};
    this.ordersBuy = {};
    this.ordersSell = {};
    this.history = {};
    for (const good of GOODS) {
      this.ordersBuy[good] = [];
      this.ordersSell[good] = [];
      this.history[good] = {
        volume: 0.0,
        price: this.referencePrices[good],
        observed: 0.0,
        demand: 0.0,
        supply: 0.0,
        unsold: 0.0,
        unmet: 0.0,
      };
    }
    this.consumptionSpending = 0.0;
    this.investmentSpending = 0.0;
    this.governmentSpending = 0.0;
    this.ceilings = {};
    this.floors = {};
    this.transactionCount = 0;
  }

  submitBuy(agent, good, quantity, price) {
    if (quantity > 1e-9 && price > 0) {
      this.ordersBuy[good].push({ agent, good, side: "buy", quantity, price });
    }
  }
  submitSell(agent, good, quantity, price) {
    if (quantity > 1e-9 && price > 0) {
      this.ordersSell[good].push({ agent, good, side: "sell", quantity, price });
    }
  }
  clear() {
    for (const good of GOODS) {
      this.ordersBuy[good].length = 0;
      this.ordersSell[good].length = 0;
    }
  }

  match() {
    const transactions = [];
    for (const good of GOODS) {
      const buys = this.ordersBuy[good].slice().sort((a, b) => b.price - a.price);
      const sells = this.ordersSell[good].slice().sort((a, b) => a.price - b.price);
      const demand = buys.reduce((sum, order) => sum + order.quantity, 0.0);
      const supply = sells.reduce((sum, order) => sum + order.quantity, 0.0);
      let volume = 0.0;
      let value = 0.0;

      while (buys.length && sells.length) {
        const b = buys[0];
        const s = sells[0];
        if (b.price + 1e-9 < s.price) break;
        const dealPrice = (b.price + s.price) / 2.0;
        let dealVolume = Math.min(b.quantity, s.quantity);
        const buyerCash = Math.max(b.agent.cash || 0.0, 0.0);
        if (buyerCash < dealPrice * dealVolume) {
          dealVolume = dealPrice > 0 ? buyerCash / dealPrice : 0.0;
        }
        if (s.agent instanceof Enterprise) {
          dealVolume = Math.min(dealVolume, s.agent.inv(good));
        } else if (s.agent instanceof FoodReserve) {
          dealVolume = Math.min(dealVolume, s.agent.food);
        } else if ((s.agent instanceof Worker || s.agent instanceof Capitalist) &&
                   good === "scrap") {
          dealVolume = Math.min(dealVolume, Math.max(0.0, s.agent.scrap || 0.0));
        }
        if (dealVolume <= 1e-9) {
          if (buyerCash <= 1e-9) buys.shift();
          else sells.shift();
          continue;
        }
        const amount = dealPrice * dealVolume;
        b.agent.cash -= amount;
        s.agent.cash += amount;
        this._receiveGood(b.agent, good, dealVolume);
        this._deliverGood(s.agent, good, dealVolume);

        if (b.agent instanceof Worker || b.agent instanceof Capitalist) {
          this.consumptionSpending += amount;
        }
        if (b.agent instanceof InvestmentProject) this.investmentSpending += amount;
        if (b.agent instanceof Government) this.governmentSpending += amount;
        if (b.agent instanceof Enterprise) {
          if (sectorUsesInput(b.agent.industry, good)) {
            b.agent.monthInputCost += amount;
          }
        }
        if (s.agent instanceof Enterprise) {
          s.agent.monthRevenue += amount;
          s.agent.lastSales[good] = (s.agent.lastSales[good] || 0.0) + dealVolume;
        }
        if (b.agent instanceof InvestmentProject) {
          b.agent.received[good] = (b.agent.received[good] || 0.0) + dealVolume;
        }

        transactions.push({ seller: s.agent, buyer: b.agent, good, quantity: dealVolume, price: dealPrice });
        b.quantity -= dealVolume;
        s.quantity -= dealVolume;
        volume += dealVolume;
        value += amount;
        if (b.quantity <= 1e-9) buys.shift();
        if (s.quantity <= 1e-9) sells.shift();
      }

      const observed = volume > 1e-9 ? value / volume : 0.0;
      this._updateReferencePrice(good, demand, supply, volume, value, buys, sells);
      this.history[good] = {
        volume,
        price: this.referencePrices[good],
        observed,
        demand,
        supply,
        unsold: sells.reduce((sum, order) => sum + order.quantity, 0.0),
        unmet: buys.reduce((sum, order) => sum + order.quantity, 0.0),
      };
    }
    this.transactionCount += transactions.length;
    this.clear();
    return transactions;
  }

  _updateReferencePrice(good, demand, supply, volume, value, buys, sells) {
    if (this.priceRegime === "free") {
      this._updateFreePrice(good, demand, supply, volume, value, buys, sells);
      return;
    }
    const old = this.referencePrices[good];
    let next;
    if (volume > 1e-9) {
      const observed = value / volume;
      next = 0.7 * old + 0.3 * observed;
    } else {
      next = old;
    }
    let imbalance = (demand - supply) / Math.max(demand, supply, 1.0);
    imbalance = Math.max(-1.0, Math.min(1.0, imbalance));
    next *= 1.0 + C.PRICE_STEP * imbalance;
    if (demand > 1e-9 && supply <= 1e-9) next *= 1.0 + C.PRICE_STEP;
    else if (supply > 1e-9 && demand <= 1e-9) next *= 1.0 - C.PRICE_STEP;
    const floor = this.floors[good];
    const ceiling = this.ceilings[good];
    if (floor !== undefined) next = Math.max(next, floor);
    if (ceiling !== undefined) next = Math.min(next, ceiling);
    this.referencePrices[good] = Math.max(C.PRICE_FLOOR, next);
  }

  _updateFreePrice(good, demand, supply, volume, value, buys, sells) {
    const old = this.referencePrices[good];
    const observed = volume > 1e-9 ? value / volume : 0.0;
    const cost = this.costAnchors[good] || 0.0;
    const markup = this.markupAnchors[good] ?? 0.15;
    const explicitAnchor = this.priceAnchors[good] || 0.0;
    const unmet = buys.reduce((sum, order) => sum + order.quantity, 0.0);
    const unsold = sells.reduce((sum, order) => sum + order.quantity, 0.0);
    const coverage = (volume + unsold) / Math.max(demand, 1e-9);
    let next;
    if (demand <= 1e-9 && coverage <= 0.0) {
      next = old;
    } else {
      if (explicitAnchor > 1e-9) {
        // By-products without a producing sector (scrap) are anchored to a
        // primary input (iron ore) plus current market evidence.
        const observedAnchor = observed > 0 ? observed : old;
        next = C.SCRAP_PRICE_ANCHOR_WEIGHT * explicitAnchor +
          (1.0 - C.SCRAP_PRICE_ANCHOR_WEIGHT) * observedAnchor;
      } else if (cost > 1e-9) {
        const costTarget = cost * (1.0 + markup);
        const observedAnchor = observed > 0 ? observed : old;
        next = C.FREE_COST_ANCHOR_WEIGHT * costTarget +
          C.FREE_OBSERVED_ANCHOR_WEIGHT * observedAnchor +
          C.FREE_REF_ANCHOR_WEIGHT * old;
      } else if (observed > 0) {
        next = (1.0 - C.FREE_REF_ANCHOR_WEIGHT) * observed +
          C.FREE_REF_ANCHOR_WEIGHT * old;
      } else {
        next = old;
      }
      const shortage = unmet / Math.max(demand, 1e-9);
      if (unmet > 1e-9 || (demand > 1e-9 && coverage < C.FREE_SHORTAGE_COVERAGE)) {
        const strength = Math.max(Math.min(1.0, shortage), Math.max(0.0, 1.0 - coverage));
        const step = Math.min(
          C.FREE_SHORTAGE_STEP_MAX,
          C.FREE_SHORTAGE_STEP_MIN + C.FREE_SHORTAGE_SLOPE * strength,
        );
        next *= 1.0 + step;
      } else if (unmet <= 1e-9 && coverage > C.FREE_GLUT_COVERAGE) {
        const strength = Math.min(
          1.0,
          (coverage - C.FREE_GLUT_COVERAGE) / C.FREE_GLUT_COVERAGE,
        );
        const step = Math.min(
          C.FREE_GLUT_STEP_MAX,
          C.FREE_GLUT_STEP_MIN + C.FREE_GLUT_SLOPE * strength,
        );
        next *= 1.0 - step;
      }
    }
    const cap = INITIAL_PRICES[good] * C.FREE_PRICE_CAP_MULT;
    next = Math.min(Math.max(C.PRICE_FLOOR, next), cap);
    const floor = this.floors[good];
    const ceiling = this.ceilings[good];
    if (floor !== undefined) next = Math.max(next, floor);
    if (ceiling !== undefined) next = Math.min(next, ceiling);
    this.referencePrices[good] = Math.max(C.PRICE_FLOOR, next);
  }

  _receiveGood(agent, good, quantity) {
    if (agent instanceof Worker || agent instanceof Capitalist) {
      if (agent.monthPurchases) {
        agent.monthPurchases[good] = (agent.monthPurchases[good] || 0.0) + quantity;
      }
      if (good === "food") agent.food += quantity;
      else if (good === "meat") agent.meat += quantity;
      else if (good === "cloth") agent.cloth += quantity;
      else if (good === "building") agent.housing += quantity;
      else if (good === "service") agent.service += quantity;
      else if (good === "car") {
        agent.cars = (agent.cars || 0.0) + quantity;
        if (!Array.isArray(agent.carBatches)) agent.carBatches = [];
        agent.carBatches.push({
          key: "car",
          quantity,
          monthsLeft: C.CAR_LIFETIME_MONTHS,
        });
      } else if (good === "scrap") {
        agent.scrap = (agent.scrap || 0.0) + quantity;
      }
      return;
    }
    if (agent instanceof Government) {
      agent.inventory[good] = (agent.inventory[good] || 0.0) + quantity;
      return;
    }
    if (agent instanceof FoodReserve) {
      if (good === "food") agent.food += quantity;
      return;
    }
    if (agent instanceof Enterprise || agent instanceof InvestmentProject) {
      agent.inventory[good] = (agent.inventory[good] || 0.0) + quantity;
    }
  }

  _deliverGood(agent, good, quantity) {
    if (agent instanceof Enterprise) {
      agent.inventory[good] = Math.max(0.0, (agent.inventory[good] || 0.0) - quantity);
    } else if (agent instanceof FoodReserve && good === "food") {
      agent.food = Math.max(0.0, agent.food - quantity);
    } else if ((agent instanceof Worker || agent instanceof Capitalist) &&
               good === "scrap") {
      agent.scrap = Math.max(0.0, (agent.scrap || 0.0) - quantity);
    }
  }
}

export { Market };
