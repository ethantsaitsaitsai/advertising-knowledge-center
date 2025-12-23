{#
  Template: execution_status.sql
  Description: 執行狀態與投放控制設定
  Returns: campaign_id, execution_id, status, priority, frequency_cap, delivery_strategy
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    pc.one_campaign_id AS campaign_id,
    pc.id AS execution_id,
    pc.medianame,
    -- 執行狀態
    pc.status,
    CASE pc.status
        WHEN 'draft' THEN '草稿'
        WHEN 'requested' THEN '送審中'
        WHEN 'pending' THEN '等待執行'
        WHEN 'booked' THEN '已預定'
        WHEN 'oncue' THEN '投放中'
        WHEN 'closed' THEN '已結案'
        WHEN 'aborted' THEN '中止'
        WHEN 'trash' THEN '已刪除'
        ELSE pc.status
    END AS status_desc,

    -- 投放控制
    pc.priority,
    pc.freq AS frequency_cap,

    -- 投放策略
    pc.deliver_strategy,
    CASE pc.deliver_strategy
        WHEN 0 THEN 'Smooth (平均投放)'
        WHEN 1 THEN 'ASAP (盡快投放)'
        ELSE 'Custom'
    END AS delivery_strategy_desc,

    -- 配速控制
    pc.pacing_status,

    -- 庫存類型
    pc.inventory_types,

    -- 黑白名單
    CASE
        WHEN pc.whitelist_urls IS NOT NULL THEN 'Whitelist'
        WHEN pc.blacklist_urls IS NOT NULL THEN 'Blacklist'
        ELSE 'None'
    END AS url_filter_type,

    -- 地區/城市鎖定
    pc.superdsp_regions,
    pc.superdsp_cities,

    -- 裝置鎖定
    pc.target_devices,

    -- 天氣鎖定
    pc.weather_conditions,

    -- 日期範圍
    pc.start_date AS execution_start_date,
    pc.end_date AS execution_end_date,

    -- 預定與結案時間
    pc.booked_at,
    pc.closed AS closed_at

FROM pre_campaign pc

WHERE pc.trash = 0

    {% if campaign_ids %}
    AND pc.one_campaign_id IN ({{ campaign_ids|join(',') }})
    {% endif %}

ORDER BY pc.one_campaign_id, pc.status, pc.start_date
LIMIT 100
