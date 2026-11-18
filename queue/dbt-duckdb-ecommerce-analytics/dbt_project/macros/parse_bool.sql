{# Normalises the many spellings of booleans that source systems produce. #}
{% macro parse_bool(column_name) -%}
    case lower(trim({{ column_name }}))
        when 'true' then true when 't' then true when 'y' then true when 'yes' then true when '1' then true
        when 'false' then false when 'f' then false when 'n' then false when 'no' then false when '0' then false
    end
{%- endmacro %}
