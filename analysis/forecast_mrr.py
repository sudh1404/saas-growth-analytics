"""
Six-month MRR forecast for CloudDesk (fictional company, synthetic data).

Candidate models (all fit on month-end MRR, Jan 2024 - Dec 2025):
  naive          last observed MRR carried forward (benchmark)
  drift          random walk with drift: last value + average monthly change of the last 6 months
  linear_trend   OLS trend on the last 12 months
  holt_damped    Holt's linear exponential smoothing with damped trend
  saas_bridge    SaaS-native component model: MRR[t+1] = MRR[t] x (1 + net retention rate of the existing base)
                 + new MRR, where retention = mean of the last 6 months and new MRR follows its 12-month linear trend

Validation: rolling-origin backtest. For each origin from 2024-12 to 2025-06 the model is fit on data up to the
origin and forecasts 1-6 months ahead; MAE, RMSE and MAPE are averaged over all origin x horizon pairs.
The model with the lowest backtest MAPE is used for the final forecast.

Prediction intervals: empirical. The backtest percentage errors of the chosen model at each horizon give an error
standard deviation; the 80% and 95% bands are forecast x (1 +/- z x sd_h). With only 7 origins these intervals are
indicative, not precise.

Outputs: data/marts/mrr_forecast.parquet, reports/forecast/*.csv|md, reports/figures/forecast/*.png
"""
import json

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

import viz_style as vs
from viz_style import plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

vs.apply()
H = 6
MODEL_COLORS = dict(zip(["saas_bridge", "drift", "holt_damped", "linear_trend", "naive"], vs.SERIES))
NICE = {"saas_bridge": "SaaS bridge", "drift": "Drift", "holt_damped": "Holt (damped)", "linear_trend": "Linear trend", "naive": "Naive"}
OUT = vs.ROOT / "reports" / "forecast"
OUT.mkdir(parents=True, exist_ok=True)

with duckdb.connect(str(vs.DB), read_only=True) as con:
    k = con.sql("select month, mrr, opening_mrr, new_mrr, net_new_mrr from marts.agg_kpis_monthly order by month").df()
k["month"] = pd.to_datetime(k.month)
k = k.set_index(pd.DatetimeIndex(k.month, freq="MS"))
y = k.mrr.astype(float)


def f_naive(hist, h):
    return np.repeat(hist.mrr.iloc[-1], h)


def f_drift(hist, h):
    step = hist.mrr.diff().tail(6).mean()
    return hist.mrr.iloc[-1] + step * np.arange(1, h + 1)


def f_linear(hist, h):
    t = hist.mrr.tail(12)
    b, a = np.polyfit(np.arange(len(t)), t.values, 1)
    return a + b * (len(t) - 1 + np.arange(1, h + 1))


def f_holt(hist, h):
    return ExponentialSmoothing(hist.mrr.astype(float).values, trend="add", damped_trend=True,
                                initialization_method="estimated").fit().forecast(h)


def f_bridge(hist, h):
    # existing-base net retention per month = (closing - new) / opening
    ret = ((hist.mrr - hist.new_mrr) / hist.opening_mrr).replace([np.inf, -np.inf], np.nan).dropna().tail(6).mean()
    nm = hist.new_mrr.tail(12)
    b, a = np.polyfit(np.arange(len(nm)), nm.values, 1)
    new_fc = a + b * (len(nm) - 1 + np.arange(1, h + 1))
    out, level = [], hist.mrr.iloc[-1]
    for n_ in new_fc:
        level = level * ret + n_
        out.append(level)
    return np.array(out)


MODELS = {"naive": f_naive, "drift": f_drift, "linear_trend": f_linear, "holt_damped": f_holt, "saas_bridge": f_bridge}

# ---------------------------------------------------------------- rolling-origin backtest
rows = []
origins = pd.date_range("2024-12-01", "2025-06-01", freq="MS")
for origin in origins:
    hist = k.loc[:origin]
    actual = y.loc[origin + pd.DateOffset(months=1): origin + pd.DateOffset(months=H)]
    for name, fn in MODELS.items():
        fc = fn(hist, H)
        for i, (m, a) in enumerate(actual.items()):
            rows.append({"model": name, "origin": origin, "month": m, "horizon": i + 1,
                         "actual": a, "forecast": fc[i], "error": fc[i] - a, "pct_error": (fc[i] - a) / a})
bt = pd.DataFrame(rows)
bt.to_csv(OUT / "backtest_predictions.csv", index=False)
score = (bt.groupby("model")
         .apply(lambda d: pd.Series({"MAE": d.error.abs().mean(), "RMSE": np.sqrt((d.error ** 2).mean()),
                                     "MAPE": d.pct_error.abs().mean(), "bias_pct": d.pct_error.mean(),
                                     "n_forecasts": len(d)}), include_groups=False)
         .sort_values("MAPE"))
by_h = bt.pivot_table(index="horizon", columns="model", values="pct_error", aggfunc=lambda s: s.abs().mean())
score.to_csv(OUT / "backtest_scores.csv")
by_h.to_csv(OUT / "backtest_mape_by_horizon.csv")
best = score.index[0]
print("Backtest (rolling origin, 1-6 months ahead):")
print(score.round(3).to_string())
print(f"\nSelected model: {best}")

# ---------------------------------------------------------------- final forecast with empirical intervals
fc = MODELS[best](k, H)
months = pd.date_range(y.index[-1] + pd.DateOffset(months=1), periods=H, freq="MS")
sd = bt[bt.model == best].groupby("horizon").pct_error.std().reindex(range(1, H + 1)).ffill()
bias = bt[bt.model == best].groupby("horizon").pct_error.mean().reindex(range(1, H + 1)).ffill()
res = pd.DataFrame({"month": months, "horizon": range(1, H + 1), "mrr_forecast": fc,
                    "lower_80": fc * (1 - 1.2816 * sd.values), "upper_80": fc * (1 + 1.2816 * sd.values),
                    "lower_95": fc * (1 - 1.96 * sd.values), "upper_95": fc * (1 + 1.96 * sd.values)})
res["arr_forecast"] = res.mrr_forecast * 12
res["model"] = best
alt = {name: MODELS[name](k, H) for name in MODELS}

# Power BI table: actuals + forecast on one axis
pbi = pd.concat([
    pd.DataFrame({"month": y.index, "series": "Actual", "mrr": y.values}),
    # anchor row: the forecast line starts at the last actual month so the two lines join in Power BI
    pd.DataFrame({"month": [y.index[-1]], "series": "Forecast", "mrr": [y.iloc[-1]], "lower_80": [y.iloc[-1]],
                  "upper_80": [y.iloc[-1]], "lower_95": [y.iloc[-1]], "upper_95": [y.iloc[-1]]}),
    pd.DataFrame({"month": months, "series": "Forecast", "mrr": fc,
                  "lower_80": res.lower_80, "upper_80": res.upper_80,
                  "lower_95": res.lower_95, "upper_95": res.upper_95}),
], ignore_index=True)
pbi["model"] = best
vs.MARTS_OUT.mkdir(parents=True, exist_ok=True)
pbi.to_parquet(vs.MARTS_OUT / "mrr_forecast.parquet", index=False)
res.to_csv(OUT / "mrr_forecast.csv", index=False)
print(res.round(0).to_string(index=False))

# ---------------------------------------------------------------- charts
fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1.6, 1]})
ax = axes[0]
ax.plot(y.index, y.values, color=vs.NAVY, lw=2.4, label="Actual MRR")
ax.fill_between(months, res.lower_95, res.upper_95, color=vs.SERIES[0], alpha=0.12, label="95% interval", lw=0)
ax.fill_between(months, res.lower_80, res.upper_80, color=vs.SERIES[0], alpha=0.22, label="80% interval", lw=0)
ax.plot([y.index[-1], *months], [y.iloc[-1], *fc], color=vs.SERIES[0], lw=2.2, ls="--", label=f"Forecast ({NICE[best]})")
for o, c in zip(["2025-03-01", "2025-06-01"], [vs.SERIES[2], vs.SERIES[1]]):
    d = bt[(bt.model == best) & (bt.origin == o)]
    ax.plot(d.month, d.forecast, color=c, lw=1.4, ls=":", marker="o", markersize=3,
            label=f"Backtest from {pd.Timestamp(o):%b %Y}")
ax.yaxis.set_major_formatter(FuncFormatter(vs.money))
ax.legend(fontsize=8, loc="upper left")
ax.annotate(f"{vs.money(fc[-1])} MRR\n({vs.money(fc[-1] * 12)} ARR)\nby {months[-1]:%b %Y}", (months[-1], fc[-1]),
            xytext=(-30, -95), textcoords="offset points", ha="right", fontsize=8.5,
            arrowprops=dict(arrowstyle="-", color=vs.TEXT_2))
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
ax.set_title(f"MRR is projected to reach {vs.money(fc[-1])} by {months[-1]:%B %Y} ({fc[-1] / y.iloc[-1] - 1:+.0%})")
vs.subtitle(ax, "Where is recurring revenue heading? Actual vs forecast, with backtest forecasts from earlier origins")
ax = axes[1]
for name in score.index:
    ax.plot(by_h.index, by_h[name], marker="o", markersize=4, color=MODEL_COLORS[name], label=NICE[name],
            lw=2.6 if name == best else 1.4)
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
ax.set_xlabel("Forecast horizon (months ahead)")
ax.set_ylabel("Mean absolute % error")
ax.legend(fontsize=8)
ax.set_title(f"{NICE[best]} has the lowest error ({score.loc[best, 'MAPE']:.1%} MAPE)")
vs.subtitle(ax, "Which method forecasts best? Rolling-origin backtest error by horizon")
vs.footnote(fig)
vs.save(fig, "mrr_forecast", "forecast")

# ---------------------------------------------------------------- report
lines = "\n".join(f"| {m} | {r.MAE:,.0f} | {r.RMSE:,.0f} | {r.MAPE:.2%} | {r.bias_pct:+.2%} |" for m, r in score.iterrows())
fl = "\n".join(f"| {r.month:%b %Y} | ${r.mrr_forecast:,.0f} | ${r.lower_80:,.0f} - ${r.upper_80:,.0f} | "
               f"${r.lower_95:,.0f} - ${r.upper_95:,.0f} | ${r.arr_forecast:,.0f} |" for r in res.itertuples())
others = ", ".join(f"{n.replace('_', ' ')} {vs.money(v[-1])}" for n, v in alt.items() if n != best)
md = f"""# MRR forecast (next 6 months)

> Fictional company, synthetic data. Generated by `analysis/forecast_mrr.py`.

## Result
Selected model: **{best.replace('_', ' ')}** (lowest rolling-origin backtest MAPE). MRR is projected to grow from
**${y.iloc[-1]:,.0f}** (Dec 2025) to **${fc[-1]:,.0f}** in {months[-1]:%B %Y} ({fc[-1] / y.iloc[-1] - 1:+.1%}),
an ARR run-rate of **${fc[-1] * 12:,.0f}**. For reference, the other methods end at: {others}.

| Month | Forecast MRR | 80% interval | 95% interval | ARR run-rate |
|---|---:|---:|---:|---:|
{fl}

## Backtest (rolling origin {origins[0]:%b %Y} - {origins[-1]:%b %Y}, horizons 1-6)
| model | MAE | RMSE | MAPE | bias |
|---|---:|---:|---:|---:|
{lines}

Positive bias = the model over-forecast on average.

## Assumptions
- **SaaS bridge model:** the existing customer base keeps its recent (6-month average) monthly net retention, and new
  MRR keeps following its 12-month linear trend. No price changes, launches or large marketing shifts.
- The pricing-page change recommended by the A/B test is **not** included; it would add upside to new MRR.
- Prediction intervals come from the chosen model's own backtest errors by horizon.

## Limitations
- Only 24 months of history, the first months being the company's ramp-up; seasonality cannot be estimated reliably.
- Seven backtest origins make the error estimates and intervals indicative only.
- Point forecasts are conditional on the business continuing as observed; churn shocks or macro changes are not modelled.

![forecast](../figures/forecast/mrr_forecast.png)
"""
(OUT / "forecast_report.md").write_text(md, encoding="utf-8")
(OUT / "forecast_results.json").write_text(json.dumps({"selected_model": best, "scores": score.to_dict(orient="index"),
                                                        "forecast": res.assign(month=res.month.astype(str)).to_dict(orient="records")},
                                                       indent=2, default=float), encoding="utf-8")
