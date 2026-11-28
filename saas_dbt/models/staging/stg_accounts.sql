-- Cleaned accounts: one row per signed-up account.
-- Fixes: channel casing, country aliases + missing values, padded industry, missing company size.
select
    account_id,
    cast(signup_date as date)                                    as signup_date,
    cast(date_trunc('month', cast(signup_date as date)) as date) as signup_month,
    lower(trim(acquisition_channel))                             as acquisition_channel,
    case
        when country is null                                   then 'Unknown'
        when lower(trim(country)) in ('usa', 'u.s.', 'united states') then 'United States'
        when lower(trim(country)) in ('uk', 'u.k.', 'united kingdom')  then 'United Kingdom'
        when lower(trim(country)) in ('in', 'india')           then 'India'
        when lower(trim(country)) in ('deutschland', 'germany') then 'Germany'
        when lower(trim(country)) in ('brasil', 'brazil')      then 'Brazil'
        when lower(trim(country)) in ('au', 'australia')       then 'Australia'
        else 'Unknown'
    end                                                          as country,
    coalesce(company_size, 'Unknown')                            as company_size,
    case
        when company_size in ('1-10', '11-50') then 'SMB'
        when company_size = '51-200'           then 'Mid-Market'
        when company_size = '201+'             then 'Enterprise'
        else 'Unknown'
    end                                                          as customer_segment,
    trim(industry)                                               as industry,
    cast(pricing_page_variant as varchar)                        as pricing_page_variant
from {{ source('raw', 'accounts') }}
