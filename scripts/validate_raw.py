"""
Validate the raw synthetic CSVs before they are loaded into the warehouse.

Two kinds of checks:
  HARD  - structural integrity (primary keys, foreign keys, date ranges, non-negative money,
          non-overlapping subscriptions, invoice/payment consistency). Any failure exits 1.
  INFO  - profile of the *intentional* data-quality issues the generator injects
          (missing / aliased countries, inconsistent casing, duplicate events, ...).
          These are expected and are cleaned in the dbt staging layer.

Writes reports/data_quality/raw_validation.md
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "reports" / "data_quality"
LO, HI = pd.Timestamp("2024-01-01"), pd.Timestamp("2026-01-31")


def load(name, dates=()):
    return pd.read_csv(RAW / f"{name}.csv", parse_dates=list(dates))


def main():
    plans = load("plans")
    acc = load("accounts", ["signup_date"])
    web = load("web_traffic", ["traffic_date"])
    mkt = load("marketing_spend", ["spend_date"])
    ev = load("events", ["event_ts"])
    subs = load("subscriptions", ["start_date", "end_date"])
    inv = load("invoices", ["invoice_date", "due_date"])
    pay = load("payments", ["attempted_at"])
    use = load("usage_monthly", ["usage_month"])

    hard = []

    def check(name, failures):
        hard.append((name, int(failures)))

    # primary keys
    for df, key, label in [(plans, ["plan_id"], "plans"), (acc, ["account_id"], "accounts"),
                           (ev, ["event_id"], "events"), (subs, ["subscription_id"], "subscriptions"),
                           (inv, ["invoice_id"], "invoices"), (pay, ["payment_id"], "payments"),
                           (use, ["account_id", "usage_month"], "usage_monthly"),
                           (web, ["traffic_date", "channel"], "web_traffic")]:
        check(f"PK unique: {label}({', '.join(key)})", df.duplicated(key).sum() + df[key].isna().any(axis=1).sum())

    # foreign keys
    ids = set(acc.account_id)
    check("FK events.account_id -> accounts", (~ev.account_id.isin(ids)).sum())
    check("FK subscriptions.account_id -> accounts", (~subs.account_id.isin(ids)).sum())
    check("FK subscriptions.plan_id -> plans", (~subs.plan_id.isin(plans.plan_id)).sum())
    check("FK invoices.subscription_id -> subscriptions", (~inv.subscription_id.isin(subs.subscription_id)).sum())
    check("FK payments.invoice_id -> invoices", (~pay.invoice_id.isin(inv.invoice_id)).sum())
    check("FK usage.account_id -> paying accounts", (~use.account_id.isin(subs.account_id)).sum())

    # ranges and values
    check("signup_date within 2024-01-01..2025-12-31", (~acc.signup_date.between(LO, "2025-12-31")).sum())
    check("event_ts within range", (~ev.event_ts.between(LO, HI)).sum())
    check("invoice_date within range", (~inv.invoice_date.between(LO, HI)).sum())
    check("non-negative invoice amount", (inv.amount < 0).sum())
    check("non-negative marketing spend", (mkt.spend < 0).sum())
    check("clicks <= impressions", (mkt.clicks > mkt.impressions).sum())
    check("non-negative visitors", (web.visitors < 0).sum())
    check("subscription start < end", (subs.end_date.notna() & (subs.end_date <= subs.start_date)).sum())

    s = subs.sort_values(["account_id", "start_date"])
    prev_end = s.groupby("account_id").end_date.shift()
    check("no overlapping subscriptions per account", (prev_end.notna() & (s.start_date < prev_end)).sum())

    paid_inv = set(pay.loc[pay.status == "succeeded", "invoice_id"])
    check("every invoice has >=1 payment attempt", (~inv.invoice_id.isin(pay.invoice_id)).sum())
    check("invoice status consistent with payment attempts",
          ((inv.status == "paid") != inv.invoice_id.isin(paid_inv)).sum())
    first_paid = ev[ev.event_name == "subscription_started"].account_id
    check("every subscriber has a subscription_started event", (~subs.account_id.isin(first_paid)).sum())

    # intentional issues (informational)
    canon = {"India", "United States", "United Kingdom", "Germany", "Brazil", "Australia"}
    info = [
        ("accounts with missing country", acc.country.isna().sum()),
        ("accounts with non-canonical country spelling", (acc.country.notna() & ~acc.country.isin(canon)).sum()),
        ("accounts with upper-case channel", (acc.acquisition_channel != acc.acquisition_channel.str.lower()).sum()),
        ("accounts with padded industry", (acc.industry != acc.industry.str.strip()).sum()),
        ("accounts with missing company_size", acc.company_size.isna().sum()),
        ("duplicate tracking events (same account, name, ts)",
         ev.duplicated(["account_id", "event_name", "event_ts"]).sum()),
        ("duplicate marketing spend rows", mkt.duplicated().sum()),
        ("usage rows with missing sessions (tracking outage)", use.sessions.isna().sum()),
        ("failed payment attempts", (pay.status == "failed").sum()),
        ("invoices unpaid after dunning", (inv.status == "failed").sum()),
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# Raw data validation report", "",
             "Synthetic data for the fictional company CloudDesk. Generated by `scripts/validate_raw.py`.", "",
             "## Row counts", "", "| table | rows |", "|---|---:|"]
    for name, df in [("plans", plans), ("accounts", acc), ("web_traffic", web), ("marketing_spend", mkt),
                     ("events", ev), ("subscriptions", subs), ("invoices", inv), ("payments", pay),
                     ("usage_monthly", use)]:
        lines.append(f"| {name} | {len(df):,} |")
    lines += ["", "## Hard checks (must pass)", "", "| check | failing rows | result |", "|---|---:|---|"]
    lines += [f"| {c} | {f:,} | {'PASS' if f == 0 else 'FAIL'} |" for c, f in hard]
    lines += ["", "## Intentional data-quality issues (cleaned in dbt staging)", "", "| issue | rows |", "|---|---:|"]
    lines += [f"| {c} | {int(v):,} |" for c, v in info]
    (OUT / "raw_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    failed = [c for c, f in hard if f]
    for c, f in hard:
        print(f"{'PASS' if f == 0 else 'FAIL'}  {c}" + (f"  ({f} rows)" if f else ""))
    for c, v in info:
        print(f"INFO  {c}: {int(v):,}")
    if failed:
        sys.exit(f"{len(failed)} hard validation check(s) failed")
    print(f"\nAll {len(hard)} hard checks passed.")


if __name__ == "__main__":
    main()
