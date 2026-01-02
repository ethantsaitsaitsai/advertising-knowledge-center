{#
  Template: industry_format_budget.sql
  Description: 多維度預算分佈統計 (支援 產業/客戶/代理商 <-> 格式 的雙向分析)
  Data Source: cue_list_budgets (Investment Budget) via pre_campaign joins
  Returns: col1 (Subject), col2 (Object), total_budget, campaign_count
  Parameters:
    - dimension: 'industry' | 'sub_industry' | 'client' | 'agency' (default: 'industry')
    - split_by_format: bool (default: True) - 若為 False，則不區分格式，僅針對維度聚合
    - primary_view: 'dimension' | 'format' (default: 'dimension') - 決定第一欄是維度還是格式
    - industry_ids: List[int] (optional)
    - sub_industry_ids: List[int] (optional)
    - client_ids: List[int] (optional)
    - agency_ids: List[int] (optional)
    - format_ids: List[int] (optional)
    - start_date: str (optional)
    - end_date: str (optional)
    - limit: int (default 100)
#}

SELECT
    -- 根據 primary_view 決定欄位順序
    {% if primary_view == 'format' %}
        -- Format First Mode
        {% if split_by_format|default(true) %}
            COALESCE(aft.title, aft.name, 'Other') AS format_name,
            aft.id AS format_id,
        {% else %}
            'All Formats' AS format_name,
            0 AS format_id,
        {% endif %}

        {% if dimension == 'client' %}
            COALESCE(c.advertiser_name, c.company) AS dimension_name,
        {% elif dimension == 'agency' %}
            COALESCE(ag.agencyname, 'Direct Client') AS dimension_name,
        {% elif dimension == 'sub_industry' %}
            pcsc.name AS dimension_name,
        {% else %}
            pcc.name AS dimension_name,
        {% endif %}

    {% else %}
        -- Dimension First Mode (Default)
        {% if dimension == 'client' %}
            COALESCE(c.advertiser_name, c.company) AS dimension_name,
        {% elif dimension == 'agency' %}
            COALESCE(ag.agencyname, 'Direct Client') AS dimension_name,
        {% elif dimension == 'sub_industry' %}
            pcsc.name AS dimension_name,
        {% else %}
            pcc.name AS dimension_name,
        {% endif %}

        {% if split_by_format|default(true) %}
            COALESCE(aft.title, aft.name, 'Other') AS format_name,
            aft.id AS format_id,
        {% else %}
            'All Formats' AS format_name,
            0 AS format_id,
        {% endif %}
    {% endif %}

    -- 統計數據
    SUM(clb.budget) AS total_budget,
    COUNT(DISTINCT oc.id) AS campaign_count

FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
LEFT JOIN clients c ON cl.client_id = c.id
LEFT JOIN agency ag ON cl.agency_id = ag.id
JOIN pre_campaign pc ON pc.one_campaign_id = oc.id
JOIN pre_campaign_categories pcc ON pc.category_id = pcc.id
LEFT JOIN pre_campaign_sub_categories pcsc ON pc.sub_category_id = pcsc.id

-- 關聯格式與預算
JOIN cue_list_product_lines clpl ON clpl.cue_list_id = cl.id
JOIN cue_list_ad_formats claf ON claf.cue_list_product_line_id = clpl.id
JOIN ad_format_types aft ON claf.ad_format_type_id = aft.id
JOIN cue_list_budgets clb ON clb.cue_list_ad_format_id = claf.id

WHERE 1=1
    AND cl.status IN ('converted', 'requested')
    AND aft.title NOT LIKE '%已退役%'

    {% if industry_ids %}
    AND pc.category_id IN ({{ industry_ids|join(',') }})
    {% endif %}

    {% if sub_industry_ids %}
    AND pc.sub_category_id IN ({{ sub_industry_ids|join(',') }})
    {% endif %}

    {% if client_ids %}
    AND c.id IN ({{ client_ids|join(',') }})
    {% endif %}
    
    {% if agency_ids %}
    AND cl.agency_id IN ({{ agency_ids|join(',') }})
    {% endif %}

    {% if format_ids %}
    AND aft.id IN ({{ format_ids|join(',') }})
    {% endif %}

    {% if start_date %}
    AND cl.end_date >= '{{ start_date }}'
    {% endif %}

    {% if end_date %}
    AND cl.start_date <= '{{ end_date }}'
    {% endif %}

GROUP BY 
    -- Group By 順序其實不影響聚合結果，但為了邏輯一致性可調整
    {% if primary_view == 'format' %}
        format_name, aft.id, dimension_name
    {% else %}
        dimension_name, format_name, aft.id
    {% endif %}

ORDER BY total_budget DESC
LIMIT {{ limit|default(100) }}