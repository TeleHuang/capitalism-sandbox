/*
 * EcoSim V0.6 · engine source — module 15: government / central bank state
 * and the three historical policy regimes. Behaviour lives in the Engine;
 * this module owns the accounts and flags only.
 */
import { GOODS } from "./00-core.js";

const POLICY_REGIMES = Object.freeze({
  CLASSICAL: "classical",
  KEYNESIAN: "keynesian",
  MMT: "mmt",
});
const MONEY_REGIMES = Object.freeze({
  GOLD: "gold",
  CREDIT: "credit",
});

class Government {
  constructor(fields) {
    Object.assign(this, {
      regime: POLICY_REGIMES.CLASSICAL,
      moneyRegime: MONEY_REGIMES.GOLD,
      cash: 0.0,
      debt: 0.0,
      centralBankMoney: 0.0,
      bondHolders: new Map(),
      taxRateWage: 0.0,
      taxRateProfit: 0.0,
      uiReplacement: 0.0,
      uiDuration: 0,
      pensionTaxRate: 0.0,
      pensionReplacement: 0.0,
      pensionFund: 0.0,
      pensionContributions: 0.0,
      pensionSubsidy: 0.0,
      pensionRevenue: 0.0,
      pensionSpending: 0.0,
      pensionBalance: 0.0,
      publicInvestmentRate: 0.0,
      publicInvestmentCountercyclical: 0.0,
      jobGuarantee: false,
      jgWage: 0.0,
      jgWorkers: [],
      jgMaxWorkers: 0,
      publicCapital: 0.0,
      inventory: Object.fromEntries(GOODS.map((good) => [good, 0.0])),
      taxRevenue: 0.0,
      transfers: 0.0,
      spending: 0.0,
      interestPaid: 0.0,
      deficit: 0.0,
      publicInvestmentBudget: 0.0,
    });
    Object.assign(this, fields || {});
  }
  get active() {
    return this.regime !== POLICY_REGIMES.CLASSICAL;
  }
  get fiatMoney() {
    return this.moneyRegime === MONEY_REGIMES.CREDIT;
  }
  resetMonth() {
    this.taxRevenue = 0.0;
    this.transfers = 0.0;
    this.spending = 0.0;
    this.interestPaid = 0.0;
    this.deficit = 0.0;
    this.publicInvestmentBudget = 0.0;
    this.pensionContributions = 0.0;
    this.pensionSubsidy = 0.0;
    this.pensionRevenue = 0.0;
    this.pensionSpending = 0.0;
    this.pensionBalance = 0.0;
  }
}

export { POLICY_REGIMES, MONEY_REGIMES, Government };
