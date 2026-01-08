{#
  Template: ad_formats.sql
  Description: 廣告格式明細（雙路徑模式：同時取得投資與執行層級的 ID）
  Returns: campaign_id, format_name, format_type_id, format_type_id_exec
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT DISTINCT
    oc.id AS campaign_id,
    
    -- 格式名稱：優先顯示合約上的名稱，若無則顯示執行端的
    COALESCE(aft_cue.title, aft_cue.name, aft_exec.title, aft_exec.name, 'Unspecified') AS format_name,
    
    -- 路徑 A ID: 用於關聯預算 (Investment Budget)
    aft_cue.id AS format_type_id,
    
    -- 路徑 B ID: 用於關聯成效 (Performance Metrics)
    -- 如果執行端沒資料，回退使用合約 ID，以防萬一
    COALESCE(aft_exec.id, aft_cue.id) AS format_type_id_exec

FROM one_campaigns oc

-- 路徑 A: 合約 (Investment)
LEFT JOIN cue_lists cl ON oc.cue_list_id = cl.id
LEFT JOIN cue_list_product_lines clpl ON clpl.cue_list_id = cl.id
LEFT JOIN cue_list_ad_formats claf ON claf.cue_list_product_line_id = clpl.id
LEFT JOIN ad_format_types aft_cue ON claf.ad_format_type_id = aft_cue.id

-- 路徑 B: 執行 (Execution / Pre-Campaign)
LEFT JOIN pre_campaign pc ON pc.one_campaign_id = oc.id AND pc.trash = 0
LEFT JOIN pre_campaign_detail pcd ON pcd.pre_campaign_id = pc.id
LEFT JOIN ad_format_types aft_exec ON pcd.ad_format_type_id = aft_exec.id

WHERE 1=1
    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    -- 確保至少有一邊有資料
    AND (aft_cue.id IS NOT NULL OR aft_exec.id IS NOT NULL)

    -- 過濾已退役格式 (Robust check for title or name)
    AND (COALESCE(aft_cue.title, aft_cue.name) IS NULL OR COALESCE(aft_cue.title, aft_cue.name) NOT LIKE '%已退役%')
    AND (COALESCE(aft_exec.title, aft_exec.name) IS NULL OR COALESCE(aft_exec.title, aft_exec.name) NOT LIKE '%已退役%')

ORDER BY oc.id, format_name
LIMIT 200
