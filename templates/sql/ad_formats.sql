{#
  Template: ad_formats.sql
  Description: 廣告格式明細（從合約層級取得）
  Returns: campaign_id, format_name, format_type
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    oc.id AS campaign_id,
    -- 格式名稱（優先使用 title，次用 name）
    COALESCE(aft.title, aft.name, 'Unspecified') AS format_name,
    aft.id AS format_type_id

FROM one_campaigns oc, cue_lists cl, cue_list_product_lines clpl, cue_list_ad_formats claf, ad_format_types aft, video_seconds_options vso

WHERE oc.cue_list_id = cl.id
    AND clpl.cue_list_id = cl.id
    AND claf.cue_list_product_line_id = clpl.id
    AND claf.ad_format_type_id = aft.id
    AND claf.video_seconds_option_id = vso.id

    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

ORDER BY oc.id, aft.name
LIMIT 100
