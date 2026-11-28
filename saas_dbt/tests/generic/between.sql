{% test between(model, column_name, min_value, max_value) %}
-- Fails for non-null values outside [min_value, max_value] (e.g. rates must be within 0..1).
select * from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }})
{% endtest %}
