{#
  Template: campaign_basic.sql
  Description: 查詢單一或多個活動的詳細資訊 (Metadata)，並附帶該活動旗下的所有 Plaid 列表。
  Returns: campaign_id, client_name, brand, contract_name, campaign_name, start_date, end_date, agency_name, plaids (comma-separated)
  Parameters:
    - campaign_ids: List[int] (required)
#}

SELECT
    oc.id AS campaign_id,
    COALESCE(c.advertiser_name, c.company) AS client_name,
    c.product AS brand,
    cl.campaign_name AS contract_name,
    oc.name AS campaign_name,
    oc.start_date,
    oc.end_date,
    COALESCE(ag.agencyname, 'Direct Client') AS agency_name,
    
    -- 聚合所有 Plaid (Pre-Campaign IDs)
    GROUP_CONCAT(DISTINCT pc.id ORDER BY pc.id ASC SEPARATOR ', ') AS plaids

FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
LEFT JOIN agency ag ON cl.agency_id = ag.id
LEFT JOIN pre_campaign pc ON pc.one_campaign_id = oc.id AND pc.trash = 0

WHERE 1=1
    AND oc.status != 'deleted'
    
    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% else %}
    -- Safety: If no IDs provided, return nothing to prevent full table scan
    AND 1=0
    {% endif %}

GROUP BY oc.id
ORDER BY oc.start_date DESC
LIMIT 100