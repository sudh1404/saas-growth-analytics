-- Every active account-month's MRR must equal the list price of its plan (no discounts in this model).
select m.* from {{ ref('fct_mrr') }} m
join {{ ref('dim_plans') }} p using (plan_id)
where m.is_active and m.mrr <> p.monthly_price
