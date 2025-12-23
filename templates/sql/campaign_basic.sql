{#
  Template: campaign_basic.sql
  Description: 活動基本資訊（客戶、活動名稱、日期、預算）
  Returns: campaign_id, client_name, contract_name, campaign_name, start_date, end_date, budget, status
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (optional) - 指定 campaign IDs
    - client_names: List[str] (optional) - 客戶名稱過濾
    - start_date: str (optional) - 開始日期過濾
    - end_date: str (optional) - 結束日期過濾
#}

SELECT
    oc.id AS campaign_id,
    COALESCE(c.advertiser_name, c.company) AS client_name,
    c.product AS brand,
    cl.campaign_name AS contract_name,
    oc.name AS campaign_name,
    oc.start_date,
    oc.end_date,
    oc.budget,
    oc.status AS campaign_status,
    cl.status AS contract_status,
    -- 優化目標 ID (沒有 objectives 表，只返回 ID)
    oc.objective_id,
    -- 代理商資訊
    ag.agencyname AS agency_name

FROM one_campaigns oc, cue_lists cl, clients c, agency ag

WHERE oc.cue_list_id = cl.id
    AND cl.client_id = c.id
    AND cl.agency_id = ag.id

    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    {% if client_names %}
    AND (c.advertiser_name IN ({{ client_names|map('tojson')|join(',') }})
         OR c.company IN ({{ client_names|map('tojson')|join(',') }}))
    {% endif %}

    {% if start_date %}
    AND oc.start_date >= '{{ start_date }}'
    {% endif %}

    {% if end_date %}
    AND oc.end_date <= '{{ end_date }}'
    {% endif %}

    -- 排除測試單和已刪除的
    AND oc.is_test = 0
    AND oc.status != 'deleted'
    AND cl.status IN ('converted', 'requested')

ORDER BY oc.start_date DESC
