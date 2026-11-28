-- Every account that reached the "Became paying" funnel step must have a subscription, and vice versa.
select account_id from {{ ref('dim_accounts') }} a
left join (select distinct account_id from {{ ref('fct_funnel_steps') }} where step_order = 5) f using (account_id)
where a.is_paying_customer <> (f.account_id is not null)
