-- Calendar dimension. Extends 6 months past the snapshot so the MRR forecast can be plotted on the same axis.
select
    cast(d as date)                         as date,
    year(d)                                 as year,
    quarter(d)                              as quarter,
    'Q' || quarter(d) || ' ' || year(d)     as year_quarter,
    month(d)                                as month_num,
    strftime(d, '%b')                       as month_name,
    cast(date_trunc('month', d) as date)    as month_start,
    strftime(d, '%Y-%m')                    as year_month,
    dayofweek(d)                            as day_of_week,
    dayofweek(d) in (0, 6)                  as is_weekend,
    d <= date '{{ var("snapshot_date") }}'  as is_actual_period
from generate_series(date '2024-01-01', date '{{ var("calendar_end_date") }}', interval 1 day) t(d)
