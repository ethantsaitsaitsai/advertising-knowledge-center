{#
  Template: unified_performance.sql
  Description: 核心成效查詢，使用 ClickHouse View，主要透過 ID 進行精準過濾。
  Returns: dimensions (dynamic), clicks, effective_impressions, ctr, vtr
  Merge Key: N/A
  Parameters:
    - dimensions: List[str] (required) - 分析維度，支援 ['client_company', 'product_line', 'one_category', 'one_sub_category', 'ad_format_type', 'campaign_name', 'client_id', 'product_line_id', 'ad_format_type_id', 'plaid', 'cmpid', 'player_mode']
    - start_date: str (required) - 開始日期 (YYYY-MM-DD)
    - end_date: str (required) - 結束日期 (YYYY-MM-DD)
    - plaids: List[int] (optional) - Placement ID 過濾
    - cmpids: List[int] (optional) - Campaign ID 過濾
    - product_line_ids: List[int] (optional) - 產品線 ID 過濾
    - ad_format_type_ids: List[int] (optional) - 廣告格式 ID 過濾
    - one_categories: List[str] (optional) - 產業類別 (String) 過濾
    - one_sub_categories: List[str] (optional) - 子產業類別 (String) 過濾
    - limit: int (optional, default 100) - 回傳筆數限制
#}

SELECT
    -- 動態維度 (Dimensions)
    {%- for dim in dimensions %}
        {%- if dim == 'client_company' %}
        dictGetString('view_pid_attributes', 'client_company', toUInt64(pid)) as client_company,
        {%- elif dim == 'product_line' %}
        dictGetString('view_pid_attributes', 'product_line', toUInt64(pid)) as product_line,
        {%- elif dim == 'one_category' %}
        dictGetString('view_pid_attributes', 'one_category', toUInt64(pid)) as one_category,
        {%- elif dim == 'one_sub_category' %}
        dictGetString('view_pid_attributes', 'one_sub_category', toUInt64(pid)) as one_sub_category,
        {%- elif dim == 'client_id' %}
        dictGetInt32('view_pid_attributes', 'client_id', toUInt64(pid)) as client_id,
        {%- elif dim == 'product_line_id' %}
        dictGetInt32('view_pid_attributes', 'product_line_id', toUInt64(pid)) as product_line_id,
        {%- elif dim == 'player_mode' %}
        dictGetString('view_pid_attributes', 'player_mode', toUInt64(pid)) as player_mode,
        {%- else %}
        {{ dim }},
        {%- endif %}
    {%- endfor %}
    -- 核心關聯 ID (Internal Use)
    cmpid,
    plaid,

    -- 基礎指標
    (SUM(bannerClick) + SUM(videoClick)) AS clicks,
    
    -- 分母 (Denominator for CTR) - Optimized with multiIf
    SUM(multiIf(ad_type = 'dsp-creative', cv, impression)) AS effective_impressions,

    SUM(q100) AS total_q100_views,
    SUM(eng) AS total_engagements,

    -- 計算指標 (Calculated Metrics)
    -- CTR: 總點擊 / 分母
    if(effective_impressions > 0, (clicks / effective_impressions) * 100, 0) AS ctr,

    -- VTR: Q100觀看數 / 分母
    if(effective_impressions > 0, (total_q100_views / effective_impressions) * 100, 0) AS vtr,

    -- ER: 互動數 / 分母
    if(effective_impressions > 0, (total_engagements / effective_impressions) * 100, 0) AS er

FROM kafka.summing_ad_format_events_view

WHERE 1=1
    -- 時間範圍
    {% if start_date %}
    AND day_local >= '{{ start_date }}'
    {% endif %}
    {% if end_date %}
    AND day_local <= '{{ end_date }}'
    {% endif %}

    -- ID Filters (Primary - Native Columns)
    {% if plaids %}
    AND plaid IN ({{ plaids | join(',') }})
    {% endif %}

    {% if cmpids %}
    AND cmpid IN ({{ cmpids | join(',') }})
    {% endif %}

    -- ID Filters (Dictionary Lookups)
    {% if product_line_ids %}
    AND dictGetInt32('view_pid_attributes', 'product_line_id', toUInt64(pid)) IN ({{ product_line_ids | join(',') }})
    {% endif %}

    {% if ad_format_type_ids %}
    AND ad_format_type_id IN ({{ ad_format_type_ids | join(',') }})
    {% endif %}

    -- String Filters (Categories)
    {% if one_categories %}
    AND one_category IN (
        {%- for cat in one_categories -%}
        '{{ cat }}'{% if not loop.last %}, {% endif %}
        {%- endfor -%}
    )
    {% endif %}

    {% if one_sub_categories %}
    AND one_sub_category IN (
        {%- for sub in one_sub_categories -%}
        '{{ sub }}'{% if not loop.last %}, {% endif %}
        {%- endfor -%}
    )
    {% endif %}

GROUP BY
    {%- for dim in dimensions %}
        {%- if dim == 'client_company' %}
        client_company
        {%- elif dim == 'product_line' %}
        product_line
        {%- elif dim == 'one_category' %}
        one_category
        {%- elif dim == 'one_sub_category' %}
        one_sub_category
        {%- elif dim == 'client_id' %}
        client_id
        {%- elif dim == 'product_line_id' %}
        product_line_id
        {%- elif dim == 'player_mode' %}
        player_mode
        {%- else %}
        {{ dim }}
        {%- endif %}
        {%- if not loop.last %}, {% endif %}
    {%- endfor %},
    cmpid,
    plaid

ORDER BY clicks DESC
LIMIT {{ limit | default(100) }}
