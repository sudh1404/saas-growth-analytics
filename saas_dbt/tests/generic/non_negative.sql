{% test non_negative(model, column_name) %}
-- Fails for rows where the column is negative.
select * from {{ model }} where {{ column_name }} < 0
{% endtest %}
