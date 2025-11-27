"""
Minimal mortgage-backed security (MBS) simulator.

This script:
- Builds a pool of fixed-rate mortgages.
- Simulates monthly defaults, prepayments, and recoveries.
- Routes cashflows through a simple sequential waterfall (Senior → Mezz → Equity).
- Discounts cashflows per tranche via Monte Carlo to estimate present value.

Only standard library modules are used so it can run anywhere with Python 3.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List


# -----------------------
# Collateral definitions
# -----------------------

@dataclass
class Mortgage:
    """Plain-vanilla fixed-rate mortgage with simple default/prepay behavior."""

    balance: float        # current outstanding principal
    rate: float           # annual note rate (e.g., 0.045 for 4.5%)
    term: int             # original term in months
    remaining: int        # remaining scheduled months
    payment: float        # scheduled level payment
    alive: bool = True    # flag to stop processing when paid off/defaulted

    @classmethod
    def create(cls, principal: float, rate: float, term_months: int) -> "Mortgage":
        """
        Build a fully-amortizing loan and compute its level monthly payment.
        """
        monthly_rate = rate / 12.0
        # Standard annuity formula: P = r * PV / (1 - (1+r)^-n)
        payment = principal * monthly_rate / (1 - (1 + monthly_rate) ** (-term_months))
        return cls(principal, rate, term_months, term_months, payment)

    def step(self, cpr: float, cdr: float, recovery: float) -> Dict[str, float]:
        """
        Advance one month.

        Returns a small cashflow dict with interest, principal, and loss.
        """
        if not self.alive or self.balance <= 1e-9:
            return {"interest": 0.0, "principal": 0.0, "loss": 0.0}

        # Translate annualized CPR/CDR to their monthly equivalents.
        monthly_default = 1 - (1 - cdr) ** (1 / 12)
        monthly_prepay = 1 - (1 - cpr) ** (1 / 12)

        # Scheduled interest and principal under normal amortization.
        interest = self.balance * (self.rate / 12.0)
        scheduled_principal = min(self.payment - interest, self.balance)

        # Default check happens before prepay; if it hits, we close the loan.
        if random.random() < monthly_default:
            cash_recovered = self.balance * recovery
            credit_loss = self.balance - cash_recovered
            self.balance = 0.0
            self.alive = False
            return {"interest": 0.0, "principal": cash_recovered, "loss": credit_loss}

        # Prepayment is applied on top of scheduled principal.
        prepay_amount = (self.balance - scheduled_principal) * monthly_prepay
        total_principal = min(self.balance, scheduled_principal + prepay_amount)
        self.balance -= total_principal
        self.remaining -= 1

        if self.remaining <= 0 or self.balance <= 1e-9:
            self.alive = False

        return {"interest": interest, "principal": total_principal, "loss": 0.0}


# -----------------------
# Tranche / waterfall
# -----------------------

@dataclass
class Tranche:
    name: str
    balance: float
    coupon: float  # annual coupon

    def copy(self) -> "Tranche":
        return Tranche(self.name, self.balance, self.coupon)


def allocate_losses(loss: float, tranches: List[Tranche]) -> None:
    """
    Apply credit losses bottom-up (Equity first, then Mezz, then Senior).
    """
    for tr in reversed(tranches):
        hit = min(tr.balance, loss)
        tr.balance -= hit
        loss -= hit
        if loss <= 1e-9:
            break


def price_single_path(
    pool_factory,
    tranche_defs: List[Tranche],
    months: int,
    cpr: float,
    cdr: float,
    recovery: float,
    disc_rate: float,
) -> Dict[str, float]:
    """
    Run one Monte Carlo path: project collateral cashflows, push them through
    the waterfall, and discount each tranche's receipts.
    """
    tranches = [t.copy() for t in tranche_defs]
    mortgages: List[Mortgage] = pool_factory()
    pv: Dict[str, float] = {t.name: 0.0 for t in tranches}
    monthly_disc = disc_rate / 12.0

    for month in range(1, months + 1):
        # Stop early if all loans have paid off/defaulted.
        if not any(mt.alive for mt in mortgages):
            break

        cash_int = 0.0
        cash_prin = 0.0
        losses = 0.0
        for mt in mortgages:
            cf = mt.step(cpr, cdr, recovery)
            cash_int += cf["interest"]
            cash_prin += cf["principal"]
            losses += cf["loss"]

        # First, push realized credit losses.
        allocate_losses(losses, tranches)

        # Pay tranche interest top-down; unpaid interest is intentionally left
        # behind and then allowed to roll into the principal bucket.
        interest_available = cash_int
        interest_paid: List[float] = []
        for tr in tranches:
            due = tr.balance * tr.coupon / 12.0
            paid = min(due, interest_available)
            interest_available -= paid
            interest_paid.append(paid)

        # Principal (plus any leftover interest) pays sequentially Senior→Mezz→Equity.
        principal_available = cash_prin + interest_available
        principal_paid: List[float] = []
        for tr in tranches:
            pay = min(tr.balance, principal_available)
            tr.balance -= pay
            principal_available -= pay
            principal_paid.append(pay)

        # Discount tranche cashflows for this period.
        discount_factor = (1 + monthly_disc) ** month
        for tr, ip, pp in zip(tranches, interest_paid, principal_paid):
            pv[tr.name] += (ip + pp) / discount_factor

    return pv


# -----------------------
# Monte Carlo driver
# -----------------------

def monte_carlo(runs: int = 50) -> Dict[str, float]:
    """
    Run many paths and average present values for each tranche.
    """
    tranche_defs = [
        Tranche("Senior", 50_000_000, 0.03),
        Tranche("Mezz", 30_000_000, 0.05),
        Tranche("Equity", 20_000_000, 0.00),
    ]

    months = 360
    cpr = 0.08     # annual CPR assumption
    cdr = 0.02     # annual CDR assumption
    recovery = 0.60
    disc_rate = 0.05

    def pool_factory() -> List[Mortgage]:
        """
        Build a synthetic mortgage pool. This keeps it simple and random, but
        you could swap in actual loan tape data if available.
        """
        pool: List[Mortgage] = []
        for _ in range(400):  # ~100mm pool notional
            principal = random.uniform(180_000, 320_000)
            # Constrain rate to stay positive and near the mean.
            rate = max(0.01, random.gauss(0.045, 0.005))
            pool.append(Mortgage.create(principal, rate, term_months=360))
        return pool

    aggregate: Dict[str, float] = {t.name: 0.0 for t in tranche_defs}
    for _ in range(runs):
        pv = price_single_path(pool_factory, tranche_defs, months, cpr, cdr, recovery, disc_rate)
        for key in aggregate:
            aggregate[key] += pv[key]

    for key in aggregate:
        aggregate[key] /= runs
    return aggregate


if __name__ == "__main__":
    random.seed(1)  # reproducible example
    prices = monte_carlo(runs=30)
    for name, val in prices.items():
        print(f"{name}: ${val:,.0f}")
        