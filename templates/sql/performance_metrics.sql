{#
   Template: performance_metrics.sql
   Description: 查詢 ClickHouse 成效數據 (CTR, VTR, ER)
   Engine: ClickHouse
   Parameters:
     - start_date: 'YYYY-MM-DD' (Required)
     - end_date: 'YYYY-MM-DD' (Required)
     - dimension: 'campaign' (預設) | 'format' | 'daily'
     - cmp_ids: List[int] (Optional, 對應 cmpid)
     - format_ids: List[int] (Optional, 對應 ad_format_type_id)
#}

SELECT
    -- 1. 動態維度選擇 (Grouping Dimensions)
    {% if dimension == 'campaign' %}
        cmpid,
        campaign_name,
        -- 若需要同時看 campaign 下的不同格式表現，可在此加入 format
        ad_format_type_id,
        ad_format_type,
    {% elif dimension == 'format' %}
        ad_format_type_id,
        ad_format_type,
    {% elif dimension == 'daily' %}
        day_local,
    {% endif %}

    -- 2. 基礎指標 (Absolute Metrics)
    -- 有效曝光 (Effective Impressions) - 分母
    SUM(CASE WHEN ad_type = 'dsp-creative' THEN cv ELSE impression END) AS effective_impressions,
    
    -- 總點擊 (Clicks)
    SUM(bannerClick + videoClick) AS total_clicks,
    
    -- 影片完整觀看 (Q100 Views)
    SUM(q100) AS total_q100_views,
    
    -- 總互動 (Engagements)
    SUM(eng) AS total_engagements,

    -- 3. 成效指標 (Rates in %)
    -- CTR: (Banner點擊 + Video點擊) / 有效曝光
    if(effective_impressions > 0, 
       (SUM(bannerClick + videoClick) / effective_impressions) * 100, 
       0
    ) AS ctr,

    -- VTR: Q100觀看數 / 有效曝光
    if(effective_impressions > 0, 
       (SUM(q100) / effective_impressions) * 100, 
       0
    ) AS vtr,

    -- ER: 互動數 / 有效曝光
    if(effective_impressions > 0, 
       (SUM(eng) / effective_impressions) * 100, 
       0
    ) AS er

FROM kafka.summing_ad_format_events_view

WHERE
    -- 時間範圍過濾
    day_local BETWEEN toDate('{{ start_date }}') AND toDate('{{ end_date }}')

    -- 篩選 Campaign ID (Int32)
    {% if cmp_ids %}
        AND cmpid IN ({{ cmp_ids | join(', ') }})
    {% endif %}

    -- 篩選 Format ID (Int32)
    {% if format_ids %}
        AND ad_format_type_id IN ({{ format_ids | join(', ') }})
    {% endif %}

GROUP BY
    {% if dimension == 'campaign' %}
        cmpid,
        campaign_name,
        ad_format_type_id,
        ad_format_type
    {% elif dimension == 'format' %}
        ad_format_type_id,
        ad_format_type
    {% elif dimension == 'daily' %}
        day_local
    {% endif %}

-- 預設依照有效曝光量排序，顯示量體最大的前 100 筆
ORDER BY effective_impressions DESC
LIMIT 100