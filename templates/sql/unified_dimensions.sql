{#
  Template: unified_dimensions.sql
  Description: 維度探索查詢 (Direct Metadata Table)，用於快速查詢「有哪些...」的問題。
  Returns: dimensions (dynamic)
  Merge Key: N/A
  Parameters:
    - dimensions: List[str] (required) - 欲查詢的維度，支援 ['client_company', 'product_line', 'one_category', 'one_sub_category', 'ad_format_type', 'campaign_name', 'publisher', 'placement_name', 'client_id', 'product_line_id', 'ad_format_type_id', 'plaid', 'cmpid']
    - client_ids: List[int] (optional)
    - product_line_ids: List[int] (optional)
    - ad_format_type_ids: List[int] (optional)
    - one_categories: List[str] (optional)
    - one_sub_categories: List[str] (optional)
    - plaids: List[int] (optional)
    - cmpids: List[int] (optional)
    - limit: int (optional, default 100)
#}

SELECT DISTINCT
    {%- for dim in dimensions %}
        {{ dim }},
    {%- endfor %}
    cmpid,
    plaid

FROM mysql_gspadmin.view_pid_attributes

WHERE 1=1
    -- ID Filters
    {% if plaids %}
    AND plaid IN ({{ plaids | join(',') }})
    {% endif %}

    {% if cmpids %}
    AND cmpid IN ({{ cmpids | join(',') }})
    {% endif %}

    {% if client_ids %}
    AND client_id IN ({{ client_ids | join(',') }})
    {% endif %}

    {% if product_line_ids %}
    AND product_line_id IN ({{ product_line_ids | join(',') }})
    {% endif %}

    {% if ad_format_type_ids %}
    AND ad_format_type_id IN ({{ ad_format_type_ids | join(',') }})
    {% endif %}

    -- String Filters
    {% if one_categories %}
    AND one_category IN (
        {%- for cat in one_categories -%}
        '{{ cat }}'{% if not loop.last %}, {% endif %}
        {%- endfor -%}
    )
    {% endif %}

    {% if one_sub_categories %}
    AND one_sub_category IN (
        {%- for sub in one_sub_categories -%}
        '{{ sub }}'{% if not loop.last %}, {% endif %}
        {%- endfor -%}
    )
    {% endif %}

LIMIT {{ limit | default(100) }}
