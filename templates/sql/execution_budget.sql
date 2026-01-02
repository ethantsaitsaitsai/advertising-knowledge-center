{#
  Template: execution_budget.sql
  Description: 執行金額/認列金額（執行中或已結案）
  Data Source: pre_campaign.budget
  Status Filter: pre_campaign.status IN ('oncue', 'close') AND pre_campaign.trash = 0
  Returns: campaign_id, execution_amount, client_name, agency_name
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (optional) - 指定 campaign IDs
    - client_names: List[str] (optional) - 客戶名稱過濾
    - client_ids: List[int] (optional) - 客戶 ID 過濾
    - start_date: str (optional) - 開始日期
    - end_date: str (optional) - 結束日期
    - limit: int (optional) - 返回筆數限制
#}

SELECT
    pc.one_campaign_id AS campaign_id,

    -- 執行單資訊
    pc.id AS execution_id,

    -- 客戶與代理商資訊 (用於排名分析)
    COALESCE(c.advertiser_name, c.company) AS client_name,
    COALESCE(ag.agencyname, 'Direct Client') AS agency_name,

    -- 執行金額（認列金額）- 來自執行單
    pc.budget AS execution_amount,
    pc.onead_gift AS execution_gift,

    -- 執行日期
    pc.start_date AS execution_start_date,
    pc.end_date AS execution_end_date,

    -- 預定與結案時間
    pc.booked_at,
    pc.closed AS closed_at

FROM pre_campaign pc
JOIN one_campaigns oc ON pc.one_campaign_id = oc.id
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
LEFT JOIN agency ag ON cl.agency_id = ag.id

WHERE 1=1
    -- 執行金額定義：執行中或已結案
    AND pc.status IN ('oncue', 'close')
    AND pc.trash = 0

    {% if campaign_ids %}
    AND pc.one_campaign_id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    {% if client_ids %}
    AND c.id IN ({{ client_ids|join(',') }})
    {% endif %}

    {% if agency_ids %}
    AND cl.agency_id IN ({{ agency_ids|join(',') }})
    {% endif %}

    {% if industry_ids %}
    AND pc.category_id IN ({{ industry_ids|join(',') }})
    {% endif %}

    {% if sub_industry_ids %}
    AND pc.sub_category_id IN ({{ sub_industry_ids|join(',') }})
    {% endif %}

    {% if client_names and not client_ids %}
    AND (c.advertiser_name IN ({{ client_names|map('tojson')|join(',') }})
         OR c.company IN ({{ client_names|map('tojson')|join(',') }}))
    {% endif %}

    {% if start_date and end_date %}
    -- YTD logic: Show all historical data up to end_date (cumulative)
    AND pc.booked_at <= '{{ end_date }}'
    {% elif start_date %}
    AND pc.end_date >= '{{ start_date }}'
    {% elif end_date %}
    AND pc.booked_at <= '{{ end_date }}'
    {% endif %}

ORDER BY pc.one_campaign_id, pc.start_date DESC
LIMIT {{ limit|default(5000) }}