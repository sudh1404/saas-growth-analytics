-- Long format: one row per account per funnel step reached (feeds the Power BI funnel visual).
with f as (select * from {{ ref('int_account_funnel') }})
select account_id, 1 as step_order, 'Signed up' as step_name, signed_up_at as reached_at from f where signed_up_at is not null
union all
select account_id, 2, 'Onboarded',                 onboarded_at       from f where onboarded_at       is not null
union all
select account_id, 3, 'Created project',           project_created_at from f where project_created_at is not null
union all
select account_id, 4, 'Activated (invited teammate)', activated_at    from f where activated_at       is not null
union all
select account_id, 5, 'Became paying',             paid_at            from f where paid_at            is not null
