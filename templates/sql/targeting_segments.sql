{#
  Template: targeting_segments.sql
  Description: 數據鎖定 / 受眾標籤設定 (基於版位)
  Returns: plaid, segment_name, segment_category
  Parameters:
    - plaids: List[int] (required) - 指定 Pre-Campaign IDs
#}

SELECT
    pre.id AS plaid,
    pre.one_campaign_id AS campaign_id,
    -- 受眾標籤描述
    ts.description AS segment_name,
    ts.name AS segment_code,
    -- 受眾分類
    sc.name AS segment_category

FROM pre_campaign pre, campaign_target_pids ctp, target_segments ts
LEFT JOIN segment_categories sc ON ts.segment_category_id = sc.id

WHERE ctp.source_id = pre.id
    AND ctp.selection_id = ts.id
    AND ctp.selection_type = 'TargetSegment'

    {% if plaids %}
    AND pre.id IN ({{ plaids|join(',') }})
    {% else %}
    AND 1=0
    {% endif %}

    AND pre.trash = 0

ORDER BY pre.id, ts.description
LIMIT 5000
