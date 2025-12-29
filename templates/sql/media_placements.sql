{#
  Template: media_placements.sql
  Description: 投放媒體與版位明細（執行層級）
  Returns: campaign_id, placement_id, ad_type
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    pcd.one_campaign_id AS campaign_id,
    pcd.id AS placement_detail_id,
    pcd.pre_campaign_id AS placement_id,
    -- 廣告格式
    aft.name AS ad_format_name,
    -- 影片秒數
    pcd.flv_second AS video_seconds,
    -- 預算
    pcd.budget
FROM pre_campaign_detail pcd
JOIN pre_campaign pc ON pcd.pre_campaign_id = pc.id
LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id

WHERE pcd.enable = 1

    {% if campaign_ids %}
    AND pcd.one_campaign_id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    {% if industry_ids %}
    AND pc.category_id IN ({{ industry_ids|join(',') }})
    {% endif %}

    {% if sub_industry_ids %}
    AND pc.sub_category_id IN ({{ sub_industry_ids|join(',') }})
    {% endif %}

ORDER BY pcd.one_campaign_id DESC, pcd.pid
LIMIT {{ limit|default(100) }}
