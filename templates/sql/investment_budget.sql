{#
  Template: investment_budget.sql
  Description: 進單金額/投資金額（委刊有記錄且成功拋轉）
  Data Source: cue_list_budgets.budget
  Status Filter: cue_lists.status IN ('converted', 'requested')
  Returns: cue_list_id, campaign_id, format_name, investment_amount
  Parameters:
    - cue_list_ids: List[int] (required)
#}

SELECT
    cl.id AS cue_list_id,
    
    -- 輔助關聯 ID (一個 CueList 可能對應多個 Campaign，這裡列出其中一個或全部)
    -- 這裡為了保持金額準確，我們以 CueList + Format 為主 Key
    -- Campaign ID 僅供參考，若一對多則可能重複，但 Reporter 應以 cue_list_id 為準
    oc.id AS campaign_id,

    -- 格式資訊
    COALESCE(aft.title, aft.name, 'Unspecified') AS format_name,
    aft.id AS format_type_id,

    -- 投資金額（進單金額）
    clb.budget AS investment_amount,
    clb.budget_gift AS investment_gift

FROM cue_lists cl
JOIN one_campaigns oc ON oc.cue_list_id = cl.id
JOIN cue_list_product_lines clpl ON clpl.cue_list_id = cl.id
JOIN cue_list_ad_formats claf ON claf.cue_list_product_line_id = clpl.id
JOIN cue_list_budgets clb ON clb.cue_list_ad_format_id = claf.id
JOIN ad_format_types aft ON claf.ad_format_type_id = aft.id

WHERE 1=1
    -- 投資金額定義：委刊有記錄且成功拋轉
    AND cl.status IN ('converted', 'requested')

    -- 過濾已退役格式
    AND aft.title NOT LIKE '%已退役%'
    AND aft.name NOT LIKE '%已退役%'

    {% if cue_list_ids %}
    AND cl.id IN ({{ cue_list_ids|join(',') }})
    {% else %}
    AND 1=0
    {% endif %}

-- 避免重複：同一個 CueList 下的同一個 Format 應該只有一筆預算
-- 但 one_campaigns 可能有多筆 (e.g. 拆單)，這會導致金額重複嗎？
-- cue_list_budgets 是綁在 cue_list 上的，跟 one_campaigns 是 1:N 關係。
-- 如果 JOIN one_campaigns，金額會膨脹！
-- 修正：我們應該 GROUP BY cue_list_id, format_type_id，並只取一個 representative campaign_id
GROUP BY cl.id, aft.id, clb.id
ORDER BY cl.id DESC
LIMIT 5000