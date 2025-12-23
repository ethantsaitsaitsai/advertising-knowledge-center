{#
  Template: campaign_basic.sql
  Description: 活動基本資訊（客戶、活動名稱、日期、預算）
  Returns: campaign_id, client_name, contract_name, campaign_name, start_date, end_date, budget, status
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (optional) - 指定 campaign IDs
    - client_names: List[str] (optional) - 客戶名稱過濾
    - client_ids: List[int] (optional) - 客戶 ID 過濾
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
    oc.objective_id,
    -- 使用 LEFT JOIN 確保沒有代理商時也能查到
    COALESCE(ag.agencyname, 'Direct Client') AS agency_name

FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
LEFT JOIN agency ag ON cl.agency_id = ag.id

WHERE 1=1
    -- 排除已刪除的
    AND oc.status != 'deleted'
    AND oc.is_test = 0
    -- 放寬合約狀態限制，確保能找到歷史資料
    -- AND cl.status IN ('converted', 'requested')

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

    {% if industry_ids or sub_industry_ids %}
    AND oc.id IN (
        SELECT one_campaign_id FROM pre_campaign pc 
        WHERE pc.trash = 0
        {% if industry_ids %}
        AND pc.category_id IN ({{ industry_ids|join(',') }})
        {% endif %}
        {% if sub_industry_ids %}
        AND pc.sub_category_id IN ({{ sub_industry_ids|join(',') }})
        {% endif %}
    )
    {% endif %}

    {% if start_date %}
    AND oc.end_date >= '{{ start_date }}'
    {% endif %}

    {% if end_date %}
    AND oc.start_date <= '{{ end_date }}'
    {% endif %}

ORDER BY oc.start_date DESC
LIMIT 100