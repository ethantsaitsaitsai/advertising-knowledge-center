SELECT
    oc.id AS cmpid,
    oc.name AS Campaign_Name,
    oc.start_date,
    oc.end_date,
    SegmentInfo.Segment_Category,
    FormatInfo.Ad_Format,
    FormatInfo.ad_format_type_id,
    FormatInfo.Budget_Sum
FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
LEFT JOIN (
    -- 1. 獨立查詢格式與預算 (避免乘積)
    SELECT
        pc.one_campaign_id,
        aft.title AS Ad_Format,
        aft.id AS ad_format_type_id,
        SUM(pcd.budget) AS Budget_Sum
    FROM pre_campaign pc
    LEFT JOIN pre_campaign_detail pcd ON pc.id = pcd.pre_campaign_id
    LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id
    WHERE pcd.budget IS NOT NULL -- 確保只加總有效的預算
    GROUP BY pc.one_campaign_id, aft.title, aft.id
) AS FormatInfo ON oc.id = FormatInfo.one_campaign_id
LEFT JOIN (
    -- 2. 獨立查詢受眾 (獨立出來避免被格式乘積膨脹)
    SELECT
        pc.one_campaign_id,
        GROUP_CONCAT(DISTINCT ts.description SEPARATOR '; ') AS Segment_Category
    FROM pre_campaign pc
    JOIN campaign_target_pids ctp ON pc.id = ctp.source_id AND ctp.source_type = 'PreCampaign'
    JOIN target_segments ts ON ctp.selection_id = ts.id
    WHERE (ts.data_source IS NULL OR ts.data_source != 'keyword')
    GROUP BY pc.one_campaign_id
) AS SegmentInfo ON oc.id = SegmentInfo.one_campaign_id
WHERE
    c.company = '悠遊卡股份有限公司'
    AND oc.start_date <= '2025-12-31'
    AND oc.end_date >= '2025-01-01'
ORDER BY oc.id, FormatInfo.Ad_Format;