{#
  Template: media_placements.sql
  Description: 投放媒體與版位明細（執行層級）
  Returns: campaign_id, placement_id, pid, pid_name, media_name, ad_type
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    pcd.one_campaign_id AS campaign_id,
    pcd.id AS placement_detail_id,
    pcd.pre_campaign_id AS placement_id,
    pcd.pid,
    pcd.pid_name,
    pcd.mediaid AS media_id,
    -- 廣告類型
    pcd.ad_type,
    -- 廣告格式
    aft.name AS ad_format_name,
    -- 影片秒數
    pcd.flv_second AS video_seconds,
    -- Banner 尺寸
    pcd.banner_size,
    -- 計價模式
    pm.name AS pricing_model,
    pcd.uniprice AS unit_price,
    -- 預算
    pcd.budget,
    -- 目標數量
    pcd.impression AS target_impressions,
    pcd.play_times AS target_plays,
    -- 啟用狀態
    pcd.enable

FROM pre_campaign_detail pcd
LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id
LEFT JOIN pricing_models pm ON pcd.pricing_model_id = pm.id

WHERE pcd.enable = 1

    {% if campaign_ids %}
    AND pcd.one_campaign_id IN ({{ campaign_ids|join(',') }})
    {% endif %}

ORDER BY pcd.one_campaign_id, pcd.pid
LIMIT 100
