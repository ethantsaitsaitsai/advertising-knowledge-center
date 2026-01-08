{#
  Template: execution_budget.sql
  Description: 執行金額/認列金額（執行中或已結案）
  Data Source: pre_campaign.budget
  Status Filter: pre_campaign.status IN ('oncue', 'close') AND pre_campaign.trash = 0
  Returns: plaid, execution_amount
  Parameters:
    - plaids: List[int] (required) - 指定 Pre-Campaign IDs
#}

SELECT
    pc.id AS plaid,
    COALESCE(aft.title, aft.name, 'Unknown Format') AS format_name,
    
    -- 執行金額（認列金額）
    pc.budget AS execution_amount,
    pc.onead_gift AS execution_gift,

    -- 輔助資訊
    pc.one_campaign_id AS campaign_id,
    pc.start_date AS execution_start_date,
    pc.end_date AS execution_end_date

FROM pre_campaign pc
LEFT JOIN ad_format_types aft ON pc.ad_format_type_id = aft.id

WHERE 1=1
    -- 執行金額定義：執行中或已結案
    AND pc.status IN ('oncue', 'close')
    AND pc.trash = 0

    {% if plaids %}
    AND pc.id IN ({{ plaids|join(',') }})
    {% else %}
    AND 1=0
    {% endif %}

ORDER BY pc.id
LIMIT 5000