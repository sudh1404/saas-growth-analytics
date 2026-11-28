-- By definition every customer is retained in their first cohort month.
select * from {{ ref('agg_cohort_retention') }}
where months_since_start = 0 and retained_customers <> cohort_customers
