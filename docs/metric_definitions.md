# Metric definitions

Every KPI used in SQL (`sql/`, dbt marts), Python and Power BI (`powerbi/dax_measures.dax`) follows the definitions
below. **Snapshot date** ("today") is 2025-12-31 (dbt var `snapshot_date`). CloudDesk is fictional; data is synthetic.

## Conventions
- **Month grain.** `fct_mrr` has one row per paying account per month. `month` is the first day of the month and MRR is
  measured **at month end** (a subscription counts if `start_date <= month_end` and `end_date` is NULL or after month end).
- **Churn month** = the month containing the subscription `end_date`; that row carries `mrr = 0`.
- **Trial.** Every signup gets a 14-day trial; funnel conversion uses signups on or before 2025-12-17 so every trial is complete.
- **Activation** ("aha moment") = the account invited a teammate.

## Acquisition & funnel
| Metric | Definition | Where |
|---|---|---|
| Visitors | Unique website visitors (web analytics, channel x day) | `fct_marketing_daily.visitors` |
| Signups | Accounts created (trial started) | `dim_accounts` |
| Signup -> onboarding | onboarded / signups | A01, A03 |
| Onboarding -> activation | activated / onboarded (also reported as project -> activated, the largest leak) | A01, A05 |
| Activation -> paid | (activated AND paying) / activated | A03, A05 |
| Overall conversion | paying / signups (signup -> paid); visit -> paid = paying / visitors | A01, A03 |
| Drop-off at a step | 1 - accounts at step / accounts at previous step | A01, A05 |
| Open vs strict funnel | Open: an account counts at a step if it ever reached it. Strict (A02): only if it reached every earlier step in order and paid within 30 days | A01 vs A02 |

## Revenue
| Metric | Definition |
|---|---|
| MRR | Sum of monthly subscription value active at month end (list price; no discounts modelled) |
| ARR | 12 x MRR (run-rate) |
| New MRR | MRR in an account's first paid month |
| Expansion MRR | Positive month-over-month change for an existing account (upgrade) |
| Contraction MRR | Negative change for an account that is still paying (downgrade) |
| Churned MRR | -prev_mrr in the month an account's MRR goes to 0 |
| Reactivation MRR | MRR of an account returning after churn (0 in this dataset; kept for completeness) |
| Net New MRR | New + Expansion + Reactivation + Contraction + Churned. **Bridge identity:** Opening + Net New = Closing, every month (dbt test) |
| MRR growth rate | Net New MRR / Opening MRR |
| ARPA | MRR / active (paying) accounts at month end |
| ARPU | MRR / active seats. Seats come from product usage (latest known month per account); accounts with no usage yet are excluded from both numerator and denominator |
| NRR (12m) | MRR now from accounts that were paying 12 months ago / their MRR 12 months ago (includes expansion, contraction, churn) |
| GRR (12m) | Same base, each account capped at its starting MRR (excludes expansion); always <= NRR and <= 100% (dbt test) |

## Customers & retention
| Metric | Definition |
|---|---|
| Active customers | Accounts with MRR > 0 at month end |
| Total customers | Accounts that have ever paid |
| Monthly logo churn rate | Churned customers in month / customers paying at the start of the month. Over a period: churn events / customer-months at risk |
| Customer retention rate | 1 - monthly logo churn rate |
| Cohort | Month of first payment |
| Month-k logo retention | Cohort customers still paying k months after the cohort month / cohort size. Cells where the cohort is too young are NULL, not 0 |
| Month-k revenue retention | Cohort MRR at month k / cohort MRR in month 0 |
| Voluntary vs involuntary churn | Involuntary = subscription ended after an invoice stayed unpaid through all dunning retries |

## Unit economics
| Metric | Definition | Assumption |
|---|---|---|
| CAC (channel) | Paid-media spend of the channel / new paying customers acquired by the channel (first payment date in the period) | Media spend only: no salaries, tools or agency fees |
| Paid CAC | Spend / new customers from paid channels | Organic and referral excluded (no attributable spend) |
| Blended CAC | All spend / all new customers | |
| LTV | ARPA x gross margin / monthly logo churn rate | Gross margin **80%** (dbt var `gross_margin`); steady-state churn, no discounting, no expansion; ARPA = average MRR over active account-months of the channel |
| LTV/CAC | LTV / CAC | Rule of thumb: >= 3x healthy |
| CAC payback | CAC / (ARPA x gross margin), in months | Ignores churn during payback |
| Marketing efficiency | CPM, CPC, CTR, cost per signup, cost per customer (campaigns attributed pro-rata to clicks within channel-day) | Last-click proxy |
| Revenue / spend | Collected revenue to date from a channel's customers / its spend | |

**Why this LTV formula and its limits.** `ARPA x margin / churn` is the standard SaaS steady-state approximation
(expected lifetime = 1 / churn). It overstates LTV when churn is front-loaded (true here: ~30% of churners leave in the
first two months) and ignores expansion and the time value of money. It is used for **relative** channel comparison;
a cohort-based, discounted LTV would be preferred for financial planning.

## Segmentation (`agg_customer_segments`, active customers at the snapshot)
| Segment | Rule |
|---|---|
| Revenue quartile | NTILE(4) by collected revenue to date |
| Engagement tercile | NTILE(3) by sessions per seat over the last 3 complete usage months |
| Tenure band | 0-2, 3-5, 6-11, 12+ months since first payment |
| Rule-based risk | Score: usage down >= 30% vs prior 3 months (2), failed payment in 90 days (2), 2+ support tickets in 90 days (1), never activated (1), tenure < 3 months (1). High >= 4, Medium 2-3, Low 0-1 |
| ML risk tier | Churn model probability: High >= action threshold, Medium >= historical base rate, Low below (see `reports/churn_model/churn_model_report.md`) |

## Experimentation
| Metric | Definition |
|---|---|
| Conversion (A/B) | Test accounts that became paying / test accounts in the arm |
| Absolute / relative lift | p_B - p_A ; p_B / p_A - 1 |
| SRM | Chi-square test of observed arm sizes vs the designed 50/50 split (alarm at p < 0.01) |
| MDE | Smallest relative lift detectable with 80% power at alpha 0.05 for the achieved sample |

## Churn model economics (threshold choice)
Outreach cost **$40** per contacted customer; **25%** of contacted true churners are saved; a save preserves
**12 months x 80% margin x MRR**. These are illustrative and should be replaced with measured values.
