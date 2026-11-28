{% test expression_is_true(model, expression) %}
-- Fails for rows where the boolean expression is not true.
select * from {{ model }} where not ({{ expression }})
{% endtest %}
