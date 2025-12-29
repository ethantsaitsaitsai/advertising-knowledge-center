{#
  Template: targeting_segments.sql
  Description: 數據鎖定 / 受眾標籤設定
  Returns: campaign_id, segment_name, segment_category, data_source
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    pre.one_campaign_id AS campaign_id,
    pre.id AS placement_id,
    -- 受眾標籤描述（根據你的範例使用 description）
    ts.description AS segment_name,
    ts.name AS segment_code,
    -- 受眾分類
    sc.name AS segment_category,
    -- 數據來源
    ts.data_source

FROM pre_campaign pre, campaign_target_pids ctp, target_segments ts
LEFT JOIN segment_categories sc ON ts.segment_category_id = sc.id

WHERE ctp.source_id = pre.id
    AND ctp.selection_id = ts.id
    AND ctp.selection_type = 'TargetSegment'

    {% if campaign_ids %}
    AND pre.one_campaign_id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    AND pre.trash = 0

ORDER BY pre.one_campaign_id, ts.description
LIMIT 100
