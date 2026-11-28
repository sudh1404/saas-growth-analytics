-- Acquisition channel dimension (shared by accounts, traffic and marketing facts).
select * from (values
    ('organic',     'Organic search',     'Unpaid', false),
    ('referral',    'Customer referral',  'Unpaid', false),
    ('paid_search', 'Paid search',        'Paid',   true),
    ('paid_social', 'Paid social',        'Paid',   true),
    ('content',     'Content marketing',  'Paid',   true),
    ('partner',     'Partner / reseller', 'Paid',   true)
) t(channel, channel_name, channel_type, is_paid)
