# Mortgage-Backed Security Simulator

Minimal, single-file Python simulation of a fixed-rate mortgage pool routed through a three-tranche sequential waterfall (Senior → Mezz → Equity). Uses only the standard library plus Monte Carlo paths to produce tranche present values.

## Requirements
- Python 3.8+ (standard library only)

## Quick start
Run the script directly; it will seed the RNG for reproducibility and print discounted PVs for each tranche.

```bash
python mbs_sim.py
```

Expected output shape:

```
Senior: $XX,XXX,XXX
Mezz: $XX,XXX,XXX
Equity: $XX,XXX,XXX
```

## What the model does
- Builds ~400 random, fully amortizing 30-year mortgages (180–320k principal, Gaussian rates around 4.5%).
- Steps each loan monthly with scheduled amortization plus stochastic default (CDR), prepayment (CPR), and loss-given-default via a recovery rate.
- Pushes cashflows through a simple waterfall: losses hit Equity → Mezz → Senior; interest pays top-down; principal (plus leftover interest) pays sequentially Senior → Mezz → Equity.
- Discounts monthly tranche cashflows at a user-set discount rate and averages across Monte Carlo paths.

## Key entry points
- `monte_carlo(runs=50)`: Runs the full simulation and returns a dict of average PVs per tranche.
- `price_single_path(...)`: Projects one path of collateral + waterfall cashflows and discounts tranche receipts.
- `Mortgage.create(...)` / `Mortgage.step(...)`: Loan construction and one-month transition with default/prepay logic.

## Tuning assumptions
Adjust the following defaults inside `monte_carlo` as needed:
- `months`: projection horizon (defaults to 360).
- `cpr` / `cdr`: annualized prepayment and default assumptions.
- `recovery`: recovery rate applied on defaulted principal.
- `disc_rate`: annual discount rate for tranche PVs.
- `tranche_defs`: names, starting balances, and coupons for each tranche.

## Extending
- Swap `pool_factory` to ingest actual loan tape data instead of random generation.
- Add fees, triggers, or interest shortfall mechanisms to the waterfall.
- Expand outputs to include time series (per-period cashflows) or analytics like WAL, average life, and duration.
