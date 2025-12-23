{#
  Template: product_lines.sql
  Description: 產品線資訊
  Returns: campaign_id, product_line_name
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    oc.id AS campaign_id,
    -- 產品線名稱
    cpl.name AS product_line_name,
    cpl.description AS product_line_description

FROM one_campaigns oc, cue_lists cl, cue_list_product_lines clpl, cue_product_lines cpl

WHERE oc.cue_list_id = cl.id
    AND clpl.cue_list_id = cl.id
    AND clpl.cue_product_line_id = cpl.id

    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

ORDER BY oc.id, cpl.name
LIMIT 100
