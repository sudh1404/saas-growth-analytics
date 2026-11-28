-- Fails if any account has more than one row in the same month.
select account_id, month, count(*) as n
from {{ ref('fct_mrr') }}
group by 1, 2
having count(*) > 1
