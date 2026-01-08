{#
  Template: media_placements.sql
  Description: 投放媒體與版位明細（執行層級）
  Returns: campaign_id, placement_id, format_name, budget, placement_name
  Merge Key: campaign_id, placement_id
  Note: placement_id 對應到 ClickHouse 的 'plaid'。
  Parameters:
    - campaign_ids: List[int] (optional) - 指定 campaign IDs
    - client_ids: List[int] (optional) - 指定 client IDs
    - agency_ids: List[int] (optional) - 指定 agency IDs
    - start_date: str (optional) - 開始日期
    - end_date: str (optional) - 結束日期
#}

SELECT
    pcd.one_campaign_id AS campaign_id,
    pcd.id AS placement_detail_id,
    pcd.pre_campaign_id AS placement_id, -- Maps to ClickHouse 'plaid'
    COALESCE(aft.title, aft.name, 'Unspecified') AS format_name,
    pc.medianame AS placement_name,
    
    -- 執行預算 (Execution Budget for this placement)
    COALESCE(pc.budget, 0) AS budget

FROM pre_campaign_detail pcd
JOIN pre_campaign pc ON pcd.pre_campaign_id = pc.id
LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id

-- Optional joins for Client/Date filtering
{% if client_ids or agency_ids or start_date or end_date %}
JOIN one_campaigns oc ON pcd.one_campaign_id = oc.id
JOIN cue_lists cl ON oc.cue_list_id = cl.id
{% endif %}

WHERE pcd.enable = 1

    {% if campaign_ids %}
    AND pcd.one_campaign_id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    {% if client_ids %}
    AND cl.client_id IN ({{ client_ids|join(',') }})
    {% endif %}

    {% if agency_ids %}
    AND cl.agency_id IN ({{ agency_ids|join(',') }})
    {% endif %}

    {% if start_date %}
    AND oc.end_date >= '{{ start_date }}'
    {% endif %}

    {% if end_date %}
    AND oc.start_date <= '{{ end_date }}'
    {% endif %}

    {% if industry_ids %}
    AND pc.category_id IN ({{ industry_ids|join(',') }})
    {% endif %}

    {% if sub_industry_ids %}
    AND pc.sub_category_id IN ({{ sub_industry_ids|join(',') }})
    {% endif %}

ORDER BY pcd.one_campaign_id DESC, pcd.pid
LIMIT {{ limit|default(1000) }}