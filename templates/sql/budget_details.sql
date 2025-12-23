{#
  Template: budget_details.sql
  Description: 預算摘要（整合投資金額與執行金額的總覽）
  Returns: campaign_id, investment_total, execution_total, budget_gap
  Merge Key: campaign_id
  Note: 此 template 提供預算總覽，詳細的投資/執行金額請使用 investment_budget.sql 和 execution_budget.sql
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    oc.id AS campaign_id,

    -- L1: 合約總預算（應收帳款）
    cl.total_budget AS contract_total_budget,
    cl.external_budget AS contract_external_budget,
    cl.material_fee,
    cl.onead_gift AS contract_onead_gift,
    cl.external_gift AS contract_external_gift,

    -- L2: 活動執行預算
    oc.budget AS campaign_budget,
    oc.currency AS currency_id,
    oc.exchange_rate,

    -- 投資金額總和（進單金額）- 來自 cue_list_budgets
    COALESCE(investment_agg.total_investment, 0) AS total_investment_amount,
    COALESCE(investment_agg.total_investment_gift, 0) AS total_investment_gift,

    -- 執行金額總和（認列金額）- 來自 pre_campaign
    COALESCE(execution_agg.total_execution, 0) AS total_execution_amount,
    COALESCE(execution_agg.total_execution_gift, 0) AS total_execution_gift,

    -- 預算缺口分析
    COALESCE(investment_agg.total_investment, 0) - COALESCE(execution_agg.total_execution, 0) AS budget_gap,

    -- 預算類型
    CASE cl.gross_type
        WHEN 1 THEN 'Net'
        WHEN 2 THEN 'Gross'
        ELSE 'Unknown'
    END AS gross_type,

    -- GSP 購買標記
    CASE oc.gsp_buy
        WHEN 1 THEN 'GSP (保證型)'
        ELSE 'Non-GSP'
    END AS gsp_type

FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id

-- 聚合投資金額（進單金額）
LEFT JOIN (
    SELECT
        oc_inner.id AS campaign_id,
        SUM(clb.budget) AS total_investment,
        SUM(clb.budget_gift) AS total_investment_gift
    FROM one_campaigns oc_inner
    JOIN cue_lists cl_inner ON oc_inner.cue_list_id = cl_inner.id
    JOIN cue_list_product_lines clpl ON cl_inner.id = clpl.cue_list_id
    JOIN cue_list_ad_formats claf ON clpl.id = claf.cue_list_product_line_id
    JOIN cue_list_budgets clb ON claf.id = clb.cue_list_ad_format_id
    WHERE cl_inner.status IN ('converted', 'requested')  -- 投資金額定義
    GROUP BY oc_inner.id
) investment_agg ON oc.id = investment_agg.campaign_id

-- 聚合執行金額（認列金額）
LEFT JOIN (
    SELECT
        pc.one_campaign_id AS campaign_id,
        SUM(pc.budget) AS total_execution,
        SUM(pc.onead_gift) AS total_execution_gift
    FROM pre_campaign pc
    WHERE pc.status IN ('oncue', 'close')  -- 執行金額定義
      AND pc.trash = 0
    GROUP BY pc.one_campaign_id
) execution_agg ON oc.id = execution_agg.campaign_id

WHERE 1=1

    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

ORDER BY oc.id
LIMIT 100
