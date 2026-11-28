-- E02 | Active customers and MRR by subscription plan x company size (with row/column shares via window functions).
select
    current_plan,
    company_size,
    count(*)                                                                         as customers,
    sum(current_mrr)                                                                 as mrr,
    round(100.0 * sum(current_mrr) / sum(sum(current_mrr)) over (), 1)              as share_of_total_mrr_pct,
    round(100.0 * count(*) / sum(count(*)) over (partition by company_size), 1)     as pct_of_size_band_on_plan,
    round(avg(sessions_per_seat_3m), 1)                                              as avg_sessions_per_seat
from marts.agg_customer_segments
group by 1, 2
order by min(current_mrr) desc, company_size;
