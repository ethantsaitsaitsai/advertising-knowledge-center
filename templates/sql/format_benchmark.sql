{#
  Template: format_benchmark.sql
  Description: 格式成效基準 (Benchmark) 與排名
  Data Source: ClickHouse (summing_ad_format_events_view)
  Returns: format_name, avg_ctr, avg_vtr, rank
  Parameters:
    - start_date: str (Required)
    - end_date: str (Required)
    - cmp_ids: List[int] (Optional - 用於產業篩選)
    - format_ids: List[int] (Optional - 用於指定格式)
#}

SELECT
    ad_format_type AS format_name,
    ad_format_type_id AS format_id,

    -- 基礎量體
    SUM(CASE WHEN ad_type = 'dsp-creative' THEN cv ELSE impression END) AS total_impressions,
    SUM(bannerClick + videoClick) AS total_clicks,
    SUM(q100) AS total_q100,

    -- 成效指標 (加權平均)
    if(total_impressions > 0, (total_clicks / total_impressions) * 100, 0) AS avg_ctr,
    if(total_impressions > 0, (total_q100 / total_impressions) * 100, 0) AS avg_vtr,
    if(total_impressions > 0, (SUM(eng) / total_impressions) * 100, 0) AS avg_er

FROM kafka.summing_ad_format_events_view

WHERE
    day_local BETWEEN toDate('{{ start_date }}') AND toDate('{{ end_date }}')
    AND ad_format_type NOT LIKE '%已退役%'

    {% if cmp_ids %}
    AND cmpid IN ({{ cmp_ids | join(', ') }})
    {% endif %}

    {% if format_ids %}
    AND ad_format_type_id IN ({{ format_ids | join(', ') }})
    {% endif %}

GROUP BY
    ad_format_type,
    ad_format_type_id

-- 預設依照 CTR 排序，但 Agent 可在 Tool 層級做 Pandas 排序
ORDER BY avg_ctr DESC
LIMIT 50