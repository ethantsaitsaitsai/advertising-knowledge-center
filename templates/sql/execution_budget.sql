{#
  Template: execution_budget.sql
  Description: 執行金額/認列金額（執行中或已結案）
  Data Source: pre_campaign.budget
  Status Filter: pre_campaign.status IN ('oncue', 'close') AND pre_campaign.trash = 0
  Returns: campaign_id, execution_amount, media_name
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (optional) - 指定 campaign IDs
    - client_names: List[str] (optional) - 客戶名稱過濾
    - start_date: str (optional) - 開始日期
    - end_date: str (optional) - 結束日期
#}

SELECT
    pc.one_campaign_id AS campaign_id,

    -- 執行單資訊
    pc.id AS execution_id,
    pc.medianame AS media_name,

    -- 執行金額（認列金額）- 來自執行單
    pc.budget AS execution_amount,
    pc.onead_gift AS execution_gift,

    -- 目標數量
    pc.play_times AS target_plays,
    pc.ta_one_plus_reach AS target_reach,

    -- 執行日期
    pc.start_date AS execution_start_date,
    pc.end_date AS execution_end_date,

    -- 執行狀態
    pc.status AS execution_status,
    CASE pc.status
        WHEN 'oncue' THEN '投放中'
        WHEN 'close' THEN '已結案'
        ELSE pc.status
    END AS status_desc,

    -- 預定與結案時間
    pc.booked_at,
    pc.closed AS closed_at

FROM pre_campaign pc

WHERE 1=1
    -- 執行金額定義：執行中或已結案
    AND pc.status IN ('oncue', 'close')
    AND pc.trash = 0

    {% if campaign_ids %}
    AND pc.one_campaign_id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    {% if client_ids %}
    AND c.id IN ({{ client_ids|join(',') }})
    {% endif %}

    {% if client_names %}
    AND EXISTS (
        SELECT 1 FROM one_campaigns oc
        JOIN cue_lists cl ON oc.cue_list_id = cl.id
        JOIN clients c ON cl.client_id = c.id
        WHERE oc.id = pc.one_campaign_id
        AND (c.advertiser_name IN ({{ client_names|map('tojson')|join(',') }})
             OR c.company IN ({{ client_names|map('tojson')|join(',') }}))
    )
    {% endif %}

    {% if start_date %}
    AND pc.end_date >= '{{ start_date }}'
    {% endif %}

    {% if end_date %}
    AND pc.start_date <= '{{ end_date }}'
    {% endif %}

ORDER BY pc.one_campaign_id, pc.start_date DESC
LIMIT 100
