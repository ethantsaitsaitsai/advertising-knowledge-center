{#
  Template: investment_budget.sql
  Description: 進單金額/投資金額（委刊有記錄且成功拋轉）
  Data Source: cue_list_budgets.budget
  Status Filter: cue_lists.status IN ('converted', 'requested')
  Returns: campaign_id, format_name, investment_amount, unit_price, client_name, agency_name
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
    oc.id AS campaign_id,

    -- 格式資訊
    COALESCE(aft.title, aft.name, 'Unspecified') AS format_name,
    aft.id AS format_type_id,

    -- 投資金額（進單金額）- 來自合約預算表
    clb.budget AS investment_amount,
    clb.budget_gift AS investment_gift,

    -- 客戶與代理商資訊 (用於排名分析)
    COALESCE(c.advertiser_name, c.company) AS client_name,
    COALESCE(ag.agencyname, 'Direct Client') AS agency_name,

    -- 計價資訊
    pm.name AS pricing_model,
    clb.uniprice AS unit_price,

    -- 保證量
    clb.counting AS guaranteed_volume,

    -- 預估毛利
    clb.estimated_gross_margin,

    -- 服務費比例
    clb.service_fee_pct

FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
LEFT JOIN agency ag ON cl.agency_id = ag.id
JOIN cue_list_product_lines clpl ON clpl.cue_list_id = cl.id
JOIN cue_list_ad_formats claf ON claf.cue_list_product_line_id = clpl.id
JOIN cue_list_budgets clb ON clb.cue_list_ad_format_id = claf.id
JOIN ad_format_types aft ON claf.ad_format_type_id = aft.id
JOIN pricing_models pm ON clb.pricing_model_id = pm.id

WHERE 1=1
    -- 投資金額定義：委刊有記錄且成功拋轉
    AND cl.status IN ('converted', 'requested')

    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    {% if client_ids %}
    AND c.id IN ({{ client_ids|join(',') }})
    {% endif %}

    {% if client_names and not client_ids %}
    AND (c.advertiser_name IN ({{ client_names|map('tojson')|join(',') }})
         OR c.company IN ({{ client_names|map('tojson')|join(',') }}))
    {% endif %}

    {% if start_date %}
    AND cl.end_date >= '{{ start_date }}'
    {% endif %}

    {% if end_date %}
    AND cl.start_date <= '{{ end_date }}'
    {% endif %}

ORDER BY oc.id, aft.name
LIMIT {{ limit|default(100) }}