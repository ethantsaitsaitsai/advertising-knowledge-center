{#
  Template: industry_format_budget.sql
  Description: 多維度預算分佈統計 (支援 產業/客戶/代理商 <-> 格式 的雙向分析)
  Data Source: cue_list_budgets (Investment Budget) via pre_campaign joins
  Returns: col1 (Subject), col2 (Object), total_budget, campaign_count
  Parameters:
    - dimension: 'industry' | 'sub_industry' | 'client' | 'agency' (default: 'industry')
    - split_by_format: bool (default: True) - 強制為 True
    - primary_view: 'dimension' | 'format' (default: 'dimension')
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
        COALESCE(aft.title, aft.name, 'Other') AS format_name,
        aft.id AS format_id,

        {% if dimension == 'client' %}
            COALESCE(c.advertiser_name, c.company) AS dimension_name,
        {% elif dimension == 'agency' %}
            COALESCE(ag.agencyname, 'Direct Client') AS dimension_name,
        {% elif dimension in ['industry', 'sub_industry'] %}
            -- 使用去重後的聚合名稱
            pc_agg.dimension_name AS dimension_name,
        {% else %}
            'Unknown' AS dimension_name,
        {% endif %}

    {% else %}
        -- Dimension First Mode (Default)
        {% if dimension == 'client' %}
            COALESCE(c.advertiser_name, c.company) AS dimension_name,
        {% elif dimension == 'agency' %}
            COALESCE(ag.agencyname, 'Direct Client') AS dimension_name,
        {% elif dimension in ['industry', 'sub_industry'] %}
            pc_agg.dimension_name AS dimension_name,
        {% else %}
            'Unknown' AS dimension_name,
        {% endif %}

        COALESCE(aft.title, aft.name, 'Other') AS format_name,
        aft.id AS format_id,
    {% endif %}

    -- 核心關聯 ID (Internal Use for Merging)
    oc.id AS campaign_id,
    COALESCE(pc_id_map.plaid, 0) AS plaid,

    -- 統計數據
    SUM(clb.budget) AS total_budget,
    COUNT(DISTINCT oc.id) AS campaign_count

FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
LEFT JOIN clients c ON cl.client_id = c.id
LEFT JOIN agency ag ON cl.agency_id = ag.id

-- [CRITICAL FIX] 處理產業關聯 (防止一對多導致預算倍增)
-- 統一使用 Subquery 預先聚合產業名稱，確保 1:1 關聯，無論何種 view
{% if dimension in ['industry', 'sub_industry'] %}
    JOIN (
        SELECT 
            pc.one_campaign_id,
            GROUP_CONCAT(DISTINCT 
                {% if dimension == 'sub_industry' %} pcsc.name {% else %} pcc.name {% endif %}
                ORDER BY {% if dimension == 'sub_industry' %} pcsc.name {% else %} pcc.name {% endif %} ASC
            SEPARATOR ', ') as dimension_name
        FROM pre_campaign pc
        JOIN pre_campaign_categories pcc ON pc.category_id = pcc.id
        LEFT JOIN pre_campaign_sub_categories pcsc ON pc.sub_category_id = pcsc.id
        WHERE 1=1
        {% if industry_ids %}
            AND pc.category_id IN ({{ industry_ids|join(',') }})
        {% endif %}
        {% if sub_industry_ids %}
            AND pc.sub_category_id IN ({{ sub_industry_ids|join(',') }})
        {% endif %}
        GROUP BY pc.one_campaign_id
    ) pc_agg ON pc_agg.one_campaign_id = oc.id

{% elif industry_ids or sub_industry_ids %}
    -- 非產業維度 (Client/Agency) 但有產業篩選：使用 DISTINCT Subquery 過濾
    JOIN (
        SELECT DISTINCT one_campaign_id
        FROM pre_campaign
        WHERE 1=1
        {% if industry_ids %}
            AND category_id IN ({{ industry_ids|join(',') }})
        {% endif %}
        {% if sub_industry_ids %}
            AND sub_category_id IN ({{ sub_industry_ids|join(',') }})
        {% endif %}
    ) pc_filter ON pc_filter.one_campaign_id = oc.id
{% endif %}

-- 關聯格式與預算
-- ... (rest of joins)

JOIN cue_list_product_lines clpl ON clpl.cue_list_id = cl.id
JOIN cue_list_ad_formats claf ON claf.cue_list_product_line_id = clpl.id
JOIN ad_format_types aft ON claf.ad_format_type_id = aft.id
JOIN cue_list_budgets clb ON clb.cue_list_ad_format_id = claf.id

-- [NEW] Join pre_campaign to get plaid (for merging with ClickHouse)
-- We use a LEFT JOIN to ensure we don't lose budget rows if no placements exist yet
LEFT JOIN (
    SELECT one_campaign_id, ad_format_type_id, MIN(id) as plaid
    FROM pre_campaign
    WHERE trash = 0
    GROUP BY one_campaign_id, ad_format_type_id
) pc_id_map ON pc_id_map.one_campaign_id = oc.id AND pc_id_map.ad_format_type_id = aft.id

WHERE 1=1
    AND cl.status IN ('converted', 'requested')
    AND aft.title NOT LIKE '%已退役%'

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
    {% if primary_view == 'format' %}
        format_name, aft.id, dimension_name, oc.id, pc_id_map.plaid
    {% else %}
        dimension_name, format_name, aft.id, oc.id, pc_id_map.plaid
    {% endif %}

ORDER BY total_budget DESC
LIMIT {{ limit|default(100) }}