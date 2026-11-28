"""
Generate a realistic synthetic dataset for CloudDesk, a FICTIONAL B2B SaaS company.
All data is synthetic. Nothing here describes a real company or real customers.

Outputs (data/raw/):
  plans.csv            subscription plan catalogue
  accounts.csv         one row per signed-up account (customer acquisition attributes)
  web_traffic.csv      daily website visitors by acquisition channel (top of funnel)
  marketing_spend.csv  daily spend, impressions and clicks by paid channel and campaign
  events.csv           product/funnel events (signup, onboarding, activation, paid, support tickets)
  subscriptions.csv    subscription periods (new, upgrade, downgrade, churn) per account
  invoices.csv         monthly invoices with final collection status
  payments.csv         individual payment attempts incl. failures and dunning retries
  usage_monthly.csv    monthly active seats and sessions per paying account

The generator deliberately injects a small amount of "real world" mess (inconsistent casing,
country aliases, missing values, duplicate tracking events, re-delivered ad-platform rows,
a tracking outage) which the dbt staging layer cleans. See docs/data_dictionary.md.

Run:  python scripts/generate_data.py            (full: Jan 2024 - Dec 2025)
      python scripts/generate_data.py --small    (fast ~15% sample for CI)
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START = pd.Timestamp("2024-01-01")
END = pd.Timestamp("2025-12-31")          # snapshot date: "today" in our story
EXPERIMENT_START = pd.Timestamp("2025-07-01")
EXPERIMENT_END = pd.Timestamp("2025-09-30")
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"

PLANS = pd.DataFrame({
    "plan_id": [1, 2, 3, 4],
    "plan_name": ["Free", "Starter", "Pro", "Business"],
    "monthly_price": [0, 29, 79, 199],
    "plan_tier": [0, 1, 2, 3],
    "max_seats": [3, 10, 50, None],
})
PRICE = dict(zip(PLANS.plan_id, PLANS.monthly_price))

CHANNELS = ["organic", "paid_search", "paid_social", "referral", "content", "partner"]
CHANNEL_P = [0.30, 0.25, 0.15, 0.12, 0.10, 0.08]
# visit -> signup conversion by channel (top of funnel)
VISIT_TO_SIGNUP = {"organic": 0.025, "paid_search": 0.040, "paid_social": 0.018,
                   "referral": 0.080, "content": 0.022, "partner": 0.060}
# paid channels: campaigns with share of channel traffic, CPC (cost per click), CTR
CAMPAIGNS = {
    "paid_search": [("search_brand", 0.35, 2.60, 0.080), ("search_generic", 0.50, 4.30, 0.035),
                    ("search_competitor", 0.15, 5.40, 0.025)],
    "paid_social": [("social_linkedin", 0.55, 1.55, 0.006), ("social_meta", 0.45, 0.90, 0.010)],
    "content":     [("content_seo_articles", 0.70, 0.85, 0.020), ("content_webinars", 0.30, 1.40, 0.030)],
    "partner":     [("partner_resellers", 0.60, 7.20, 0.050), ("partner_marketplace", 0.40, 8.70, 0.040)],
}
COUNTRIES = ["India", "United States", "United Kingdom", "Germany", "Brazil", "Australia"]
COUNTRY_P = [0.28, 0.30, 0.12, 0.12, 0.10, 0.08]
COUNTRY_ALIASES = {"United States": ["USA", "U.S.", "united states"], "United Kingdom": ["UK", "U.K."],
                   "India": ["india", "IN"], "Germany": ["Deutschland"], "Brazil": ["Brasil"],
                   "Australia": ["AU"]}
SIZES = ["1-10", "11-50", "51-200", "201+"]
SIZE_P = [0.50, 0.30, 0.15, 0.05]
INDUSTRIES = ["Software", "Agency", "Education", "Retail", "Healthcare", "Finance", "Manufacturing"]

# plan mix for new paying customers, by company size  -> (Starter, Pro, Business)
PLAN_MIX = {"1-10": [0.65, 0.30, 0.05], "11-50": [0.40, 0.45, 0.15],
            "51-200": [0.20, 0.45, 0.35], "201+": [0.10, 0.35, 0.55]}
BASE_CHURN = {2: 0.026, 3: 0.018, 4: 0.010}   # monthly voluntary churn hazard by plan_id
CHANNEL_CHURN = {"paid_social": 1.30, "referral": 0.75, "partner": 0.85,
                 "organic": 1.00, "paid_search": 1.05, "content": 1.10}
SEATS_BASE = {"1-10": 3, "11-50": 12, "51-200": 40, "201+": 120}
MONTH_SEASONALITY = {1: 1.10, 2: 1.02, 3: 1.05, 4: 1.00, 5: 0.98, 6: 0.95,
                     7: 0.93, 8: 0.90, 9: 1.08, 10: 1.05, 11: 1.00, 12: 0.85}
VOLUNTARY_REASONS = ["too_expensive", "missing_features", "switched_competitor",
                     "low_usage", "business_closed"]


def main(small: bool = False, out: Path = OUT):
    rng = np.random.default_rng(SEED)
    out.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(START, END, freq="D")
    scale = 0.15 if small else 1.0

    # ---------- 1. accounts: signups grow over time, weekly + yearly seasonality ----------
    t = np.linspace(0, 1, len(days))
    season = days.month.map(MONTH_SEASONALITY).values
    lam = (25 + 35 * t) * season * np.where(days.dayofweek >= 5, 0.6, 1.0) * scale
    n_per_day = rng.poisson(lam)
    signup_dates = np.repeat(days.values, n_per_day)
    n = len(signup_dates)

    accounts = pd.DataFrame({
        "account_id": np.arange(100001, 100001 + n),
        "signup_date": pd.to_datetime(signup_dates),
        "acquisition_channel": rng.choice(CHANNELS, n, p=CHANNEL_P),
        "country": rng.choice(COUNTRIES, n, p=COUNTRY_P),
        "company_size": rng.choice(SIZES, n, p=SIZE_P),
        "industry": rng.choice(INDUSTRIES, n),
    })
    # pricing-page experiment: accounts signing up during the test window are randomised 50/50
    in_test = accounts.signup_date.between(EXPERIMENT_START, EXPERIMENT_END)
    accounts["pricing_page_variant"] = np.where(in_test, rng.choice(["A", "B"], n), None)

    # ---------- 2. funnel events ----------
    ch = accounts.acquisition_channel.values
    size = accounts.company_size.values
    p_onboard = 0.72 + np.select([ch == "referral", ch == "paid_social"], [0.08, -0.10], 0)
    p_project = np.full(n, 0.70)
    p_invite = 0.45 + np.select([size == "11-50", size == "51-200", size == "201+"], [0.08, 0.15, 0.20], 0)

    onboarded = rng.random(n) < p_onboard
    project = onboarded & (rng.random(n) < p_project)
    invited = project & (rng.random(n) < p_invite)          # "activated" = invited a teammate

    p_convert = np.select([invited, project, onboarded], [0.45, 0.25, 0.10], 0.03)
    # treatment B (annual-discount banner on pricing page) has a true +15% relative effect
    p_convert = np.where(accounts.pricing_page_variant.values == "B", p_convert * 1.15, p_convert)
    converted = rng.random(n) < p_convert

    sd = accounts.signup_date.values
    secs = lambda lo, hi: pd.to_timedelta(rng.integers(lo, hi, n), unit="s").values
    ts_signup = sd + secs(8 * 3600, 20 * 3600)
    ts_onboard = ts_signup + secs(300, 2 * 86400)
    ts_project = ts_onboard + secs(600, 3 * 86400)
    ts_invite = ts_project + secs(3600, 5 * 86400)
    ts_paid = sd + np.timedelta64(14, "D") + secs(0, 86400)   # converts when the 14-day trial ends

    ev = [("signed_up", np.ones(n, bool), ts_signup),
          ("onboarding_completed", onboarded, ts_onboard),
          ("project_created", project, ts_project),
          ("teammate_invited", invited, ts_invite),
          ("subscription_started", converted, ts_paid)]
    events = pd.concat([
        pd.DataFrame({"account_id": accounts.account_id[m], "event_name": name, "event_ts": ts[m]})
        for name, m, ts in ev
    ])

    # ---------- 3. subscriptions, invoices, payments, usage (month-by-month lifecycle) ----------
    subs, invoices, payments, usage, tickets = [], [], [], [], []
    sub_id, inv_id, pay_id = 1, 1, 1
    payers = accounts[converted].assign(activated=invited[converted])
    for a in payers.itertuples(index=False):
        start = pd.Timestamp(a.signup_date) + pd.Timedelta(days=14)
        if start > END:
            continue
        plan = int(rng.choice([2, 3, 4], p=PLAN_MIX[a.company_size]))
        seats_base = SEATS_BASE[a.company_size]
        engagement = rng.lognormal(0, 0.25) * (1.15 if a.activated else 0.85)   # account "health"
        period_start, reason = start, "new"
        churn_date, churn_reason, cursor, month_no = None, None, start, 0
        months_active = []
        p_first_fail = 0.05 + (0.03 if a.company_size == "1-10" else 0) + (0.02 if a.country == "Brazil" else 0)
        while True:
            nxt = cursor + pd.DateOffset(months=1)
            # ---- invoice + payment attempts (initial charge, then up to 2 dunning retries) ----
            final_status = "paid"
            attempt_ts = cursor.normalize() + pd.Timedelta(hours=int(rng.integers(1, 6)))
            for attempt in (1, 2, 3):
                fail_p = p_first_fail if attempt == 1 else 0.50
                ok = rng.random() >= fail_p
                reason_f = None if ok else rng.choice(["card_declined", "insufficient_funds", "expired_card"],
                                                      p=[0.5, 0.3, 0.2])
                payments.append((pay_id, inv_id, a.account_id, attempt, attempt_ts, PRICE[plan],
                                 "succeeded" if ok else "failed", reason_f))
                pay_id += 1
                if ok:
                    break
                if attempt == 3:
                    final_status = "failed"
                attempt_ts = attempt_ts + pd.Timedelta(days=3 if attempt == 1 else 4)
            invoices.append((inv_id, a.account_id, sub_id, cursor.normalize(),
                             (cursor + pd.Timedelta(days=7)).normalize(), PRICE[plan], final_status))
            inv_id += 1
            month_no += 1
            months_active.append(cursor.to_period("M").to_timestamp())
            if nxt > END:
                break
            hazard = BASE_CHURN[plan] * (0.7 if a.activated else 1.0) * CHANNEL_CHURN[a.acquisition_channel]
            hazard *= 1.2 if a.company_size == "1-10" else 1.0
            hazard *= 1.5 if month_no <= 2 else 1.0
            hazard *= 1.25 if engagement < 0.8 else (0.8 if engagement > 1.2 else 1.0)
            r = rng.random()
            if final_status == "failed" and rng.random() < 0.50:      # involuntary churn
                churn_date, churn_reason = nxt, "payment_failure"
            elif r < hazard:                                         # voluntary churn
                churn_date = nxt
                churn_reason = str(rng.choice(VOLUNTARY_REASONS, p=[0.30, 0.22, 0.20, 0.20, 0.08]))
            elif r < hazard + 0.020 * engagement and plan < 4:       # expansion (upgrade)
                subs.append((sub_id, a.account_id, plan, period_start, nxt, PRICE[plan], reason, "upgraded", None))
                sub_id += 1
                plan, period_start, reason = plan + 1, nxt, "upgrade"
            elif r < hazard + 0.020 * engagement + 0.008 and plan > 2:   # contraction (downgrade)
                subs.append((sub_id, a.account_id, plan, period_start, nxt, PRICE[plan], reason, "downgraded", None))
                sub_id += 1
                plan, period_start, reason = plan - 1, nxt, "downgrade"
            # ---- usage for the billing month just finished ----
            seats = max(1, int(seats_base * rng.uniform(0.7, 1.1)))
            sessions = max(0, int(rng.normal(seats * 9 * engagement, seats * 2)))
            usage.append([a.account_id, cursor.to_period("M").to_timestamp(), seats, sessions])
            if churn_date is not None:
                # voluntary churners disengage first: usage fades over their last 3 months
                if churn_reason != "payment_failure":
                    for back, fade in zip((1, 2, 3), (0.35, 0.55, 0.8)):
                        if len(usage) >= back and usage[-back][0] == a.account_id:
                            usage[-back][3] = int(usage[-back][3] * fade * rng.uniform(0.7, 1.3))
                break
            cursor = nxt
        # ---- support tickets: more of them in the 3 months before a voluntary churn ----
        pre_churn = set(months_active[-3:]) if churn_reason not in (None, "payment_failure") else set()
        for m in months_active:
            k = rng.poisson((0.9 if m in pre_churn else 0.25) * (1.5 if a.company_size in ("51-200", "201+") else 1))
            for _ in range(k):
                tickets.append((a.account_id, m + pd.Timedelta(days=int(rng.integers(0, 28)),
                                                              seconds=int(rng.integers(0, 86400)))))
        subs.append((sub_id, a.account_id, plan, period_start, churn_date, PRICE[plan], reason,
                     "churned" if churn_date is not None else None, churn_reason))
        sub_id += 1

    subscriptions = pd.DataFrame(subs, columns=["subscription_id", "account_id", "plan_id", "start_date",
                                                "end_date", "mrr", "start_reason", "end_reason", "churn_reason"])
    invoices = pd.DataFrame(invoices, columns=["invoice_id", "account_id", "subscription_id",
                                               "invoice_date", "due_date", "amount", "status"])
    payments = pd.DataFrame(payments, columns=["payment_id", "invoice_id", "account_id", "attempt_number",
                                               "attempted_at", "amount", "status", "failure_reason"])
    usage = pd.DataFrame(usage, columns=["account_id", "usage_month", "active_seats", "sessions"])

    tickets = pd.DataFrame(tickets, columns=["account_id", "event_ts"]).assign(event_name="support_ticket_opened")
    events = pd.concat([events, tickets[["account_id", "event_name", "event_ts"]]])
    events = events[events.event_ts <= END + pd.Timedelta(days=1)]
    events = events.sort_values(["event_ts", "account_id"]).reset_index(drop=True)
    events.insert(0, "event_id", np.arange(1, len(events) + 1))

    # ---------- 4. web traffic (visitors) and marketing spend ----------
    daily = accounts.groupby(["signup_date", "acquisition_channel"]).size().rename("signups")
    grid = pd.MultiIndex.from_product([days, CHANNELS], names=["signup_date", "acquisition_channel"])
    daily = daily.reindex(grid, fill_value=0).reset_index()
    cvr = daily.acquisition_channel.map(VISIT_TO_SIGNUP) * rng.normal(1.0, 0.12, len(daily)).clip(0.6, 1.4)
    floor = rng.poisson(lam=(40 * scale) + 1, size=len(daily))       # some traffic even on 0-signup days
    daily["visitors"] = np.maximum(np.round(daily.signups / cvr), floor).astype(int)
    daily["sessions"] = np.round(daily.visitors * rng.uniform(1.15, 1.45, len(daily))).astype(int)
    daily["pricing_page_views"] = np.round(daily.visitors * rng.uniform(0.08, 0.14, len(daily))).astype(int)
    web_traffic = daily.rename(columns={"signup_date": "traffic_date", "acquisition_channel": "channel"})[
        ["traffic_date", "channel", "visitors", "sessions", "pricing_page_views"]]

    rows = []
    for c, camps in CAMPAIGNS.items():
        vis = daily[daily.acquisition_channel == c]
        for camp, share, cpc, ctr in camps:
            clicks = np.round(vis.visitors.values * share * rng.normal(1.0, 0.05, len(vis)).clip(0.8, 1.2)).astype(int)
            spend = np.round(clicks * cpc * rng.normal(1.0, 0.10, len(vis)).clip(0.7, 1.4), 2)
            impressions = np.round(clicks / (ctr * rng.normal(1.0, 0.1, len(vis)).clip(0.7, 1.3))).astype(int)
            rows.append(pd.DataFrame({"spend_date": vis.signup_date.values, "channel": c, "campaign": camp,
                                      "impressions": impressions, "clicks": clicks, "spend": spend}))
    marketing = pd.concat(rows).sort_values(["spend_date", "channel", "campaign"]).reset_index(drop=True)

    # ---------- 5. deliberate data-quality issues (cleaned in dbt staging) ----------
    accounts["country"] = accounts.country.where(rng.random(n) > 0.01, None)          # 1% missing
    alias_mask = rng.random(n) < 0.03                                                 # 3% alias spellings
    accounts.loc[alias_mask, "country"] = accounts.loc[alias_mask, "country"].map(
        lambda c: rng.choice(COUNTRY_ALIASES[c]) if c in COUNTRY_ALIASES else c)
    accounts.loc[accounts.sample(frac=0.02, random_state=SEED).index, "acquisition_channel"] = \
        accounts.acquisition_channel.str.upper()                                       # inconsistent case
    pad = accounts.sample(frac=0.01, random_state=SEED + 1).index
    accounts.loc[pad, "industry"] = " " + accounts.loc[pad, "industry"] + " "         # stray whitespace
    accounts.loc[accounts.sample(frac=0.005, random_state=SEED + 2).index, "company_size"] = None

    dup_ev = events.sample(frac=0.004, random_state=SEED)                             # double-fired tracking
    dup_ev = dup_ev.assign(event_id=np.arange(len(events) + 1, len(events) + 1 + len(dup_ev)))
    events = pd.concat([events, dup_ev]).sort_values("event_id").reset_index(drop=True)

    marketing = pd.concat([marketing, marketing.sample(frac=0.005, random_state=SEED)])  # re-delivered rows
    marketing = marketing.sort_values(["spend_date", "channel", "campaign"]).reset_index(drop=True)

    outage = (usage.usage_month == pd.Timestamp("2025-03-01")) & (rng.random(len(usage)) < 0.04)
    usage["sessions"] = usage.sessions.astype("Int64").mask(outage)                    # tracking outage

    for name, df in [("plans", PLANS), ("accounts", accounts), ("web_traffic", web_traffic),
                     ("marketing_spend", marketing), ("events", events), ("subscriptions", subscriptions),
                     ("invoices", invoices), ("payments", payments), ("usage_monthly", usage)]:
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"{name:<16} {len(df):>9,} rows")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--small", action="store_true", help="generate ~15%% of the data (for CI)")
    p.add_argument("--out", type=Path, default=OUT, help="output folder (default data/raw)")
    a = p.parse_args()
    main(a.small, a.out)
