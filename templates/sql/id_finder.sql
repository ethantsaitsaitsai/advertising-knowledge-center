{#
  Template: id_finder.sql
  Description: 核心 ID 搜尋器。根據時間、客戶、格式等條件，找出所有相關的 IDs (CueList, Campaign, Plaid)。
  Returns: cue_list_id, campaign_id (one_campaign_id), plaid (pre_campaign_id)
  Parameters:
    - start_date: str (required)
    - end_date: str (required)
    - client_ids: List[int] (optional)
    - agency_ids: List[int] (optional)
    - ad_format_type_ids: List[int] (optional)
    - industry_ids: List[int] (optional)
    - sub_industry_ids: List[int] (optional)
    - product_line_ids: List[int] (optional)
    - limit: int (default 5000)
#}

SELECT DISTINCT
    cl.id AS cue_list_id,
    oc.id AS campaign_id,
    pc.id AS plaid

    -- 輔助資訊 (Optional, for debugging or lightweight grouping)
    -- cl.campaign_name AS contract_name,
    -- oc.name AS campaign_name,
    -- pc.ad_format_type_id

FROM cue_lists cl
JOIN one_campaigns oc ON oc.cue_list_id = cl.id
JOIN pre_campaign pc ON pc.one_campaign_id = oc.id

WHERE 1=1
    -- 基礎過濾：排除垃圾資料
    AND pc.trash = 0
    AND oc.status != 'deleted'
    
    -- 時間範圍 (Required) - 用 Pre-Campaign 的走期最準確
    AND STR_TO_DATE(pc.end_date, '%Y/%m/%d') >= '{{ start_date }}'
    AND STR_TO_DATE(pc.start_date, '%Y/%m/%d') <= '{{ end_date }}'

    -- ID Filters
    {% if client_ids %}
    AND cl.client_id IN ({{ client_ids|join(',') }})
    {% endif %}

    {% if agency_ids %}
    AND cl.agency_id IN ({{ agency_ids|join(',') }})
    {% endif %}

    {% if ad_format_type_ids %}
    AND pc.ad_format_type_id IN ({{ ad_format_type_ids|join(',') }})
    {% endif %}

    {% if product_line_ids %}
    AND cl.product_line_id IN ({{ product_line_ids|join(',') }})
    {% endif %}

    -- Industry Filters (on pre_campaign)
    {% if industry_ids %}
    AND pc.category_id IN ({{ industry_ids|join(',') }})
    {% endif %}

    {% if sub_industry_ids %}
    AND pc.sub_category_id IN ({{ sub_industry_ids|join(',') }})
    {% endif %}

ORDER BY cl.id, oc.id, pc.id
LIMIT {{ limit|default(5000) }}
