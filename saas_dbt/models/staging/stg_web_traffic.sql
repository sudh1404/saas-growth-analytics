select
    cast(traffic_date as date) as traffic_date,
    lower(trim(channel))       as channel,
    visitors,
    sessions,
    pricing_page_views
from {{ source('raw', 'web_traffic') }}
