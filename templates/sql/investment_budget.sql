{#
  Template: investment_budget.sql
  Description: 進單金額/投資金額（委刊有記錄且成功拋轉）
  Data Source: cue_list_budgets.budget
  Status Filter: cue_lists.status IN ('converted', 'requested')
  Returns: campaign_id, format_name, investment_amount, unit_price
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (optional) - 指定 campaign IDs
    - client_names: List[str] (optional) - 客戶名稱過濾
    - start_date: str (optional) - 開始日期
    - end_date: str (optional) - 結束日期
#}

SELECT
    oc.id AS campaign_id,

    -- 格式資訊
    COALESCE(aft.title, aft.name, 'Unspecified') AS format_name,
    aft.id AS format_type_id,

    -- 投資金額（進單金額）- 來自合約預算表
    clb.budget AS investment_amount,
    clb.budget_gift AS investment_gift,

    -- 計價資訊
    pm.name AS pricing_model,
    clb.uniprice AS unit_price,

    -- 保證量
    clb.counting AS guaranteed_volume,

    -- 預估毛利
    clb.estimated_gross_margin,

    -- 服務費比例
    clb.service_fee_pct

FROM one_campaigns oc, cue_lists cl, cue_list_product_lines clpl,
     cue_list_ad_formats claf, cue_list_budgets clb,
     ad_format_types aft, pricing_models pm

WHERE oc.cue_list_id = cl.id
    AND clpl.cue_list_id = cl.id
    AND claf.cue_list_product_line_id = clpl.id
    AND clb.cue_list_ad_format_id = claf.id
    AND claf.ad_format_type_id = aft.id
    AND clb.pricing_model_id = pm.id

    -- 投資金額定義：委刊有記錄且成功拋轉
    AND cl.status IN ('converted', 'requested')

    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    {% if client_names %}
    AND EXISTS (
        SELECT 1 FROM clients c
        WHERE cl.client_id = c.id
        AND (c.advertiser_name IN ({{ client_names|map('tojson')|join(',') }})
             OR c.company IN ({{ client_names|map('tojson')|join(',') }}))
    )
    {% endif %}

    {% if start_date %}
    AND cl.start_date >= '{{ start_date }}'
    {% endif %}

    {% if end_date %}
    AND cl.end_date <= '{{ end_date }}'
    {% endif %}

ORDER BY oc.id, aft.name
LIMIT 100
