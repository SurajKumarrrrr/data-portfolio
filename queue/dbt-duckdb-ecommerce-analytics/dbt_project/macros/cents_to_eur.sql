{# Source systems store money as integer cents; the warehouse uses exact DECIMAL euros. #}
{% macro cents_to_eur(column_name) -%}
    cast(cast({{ column_name }} as decimal(18, 2)) / 100 as decimal(14, 2))
{%- endmacro %}
