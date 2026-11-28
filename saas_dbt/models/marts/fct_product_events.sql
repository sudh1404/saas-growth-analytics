-- De-duplicated product and funnel events.
select * from {{ ref('stg_events') }}
