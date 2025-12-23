{#
  Template: contract_kpis.sql
  Description: 合約承諾 KPI（CTR, VTR, CVR, ER 的上下限）
  Returns: campaign_id, format_name, ctr_lb, ctr_ub, vtr_lb, vtr_ub, cvr_lb, cvr_ub
  Merge Key: campaign_id
  Parameters:
    - campaign_ids: List[int] (required) - 指定 campaign IDs
#}

SELECT
    oc.id AS campaign_id,
    -- 格式名稱（用於區分不同格式的 KPI）
    COALESCE(aft.title, aft.name, 'Overall') AS format_name,

    -- CTR 保證範圍
    clb.ctr_lb AS ctr_lower_bound,
    clb.ctr_ub AS ctr_upper_bound,

    -- VTR 保證範圍
    clb.vtr_lb AS vtr_lower_bound,
    clb.vtr_ub AS vtr_upper_bound,

    -- CVR 保證範圍
    clb.cvr_lb AS cvr_lower_bound,
    clb.cvr_ub AS cvr_upper_bound,

    -- ER 保證範圍
    clb.er_lb AS er_lower_bound,
    clb.er_ub AS er_upper_bound,

    -- 保證量
    clb.counting AS guaranteed_count,

    -- 計價模式
    pm.name AS pricing_model,
    clb.uniprice AS unit_price,
    clb.budget AS budget_for_this_format,

    -- 預估毛利
    clb.estimated_gross_margin

FROM one_campaigns oc, cue_lists cl, cue_list_product_lines clpl, cue_list_ad_formats claf, cue_list_budgets clb, ad_format_types aft, pricing_models pm

WHERE oc.cue_list_id = cl.id
    AND clpl.cue_list_id = cl.id
    AND claf.cue_list_product_line_id = clpl.id
    AND clb.cue_list_ad_format_id = claf.id
    AND claf.ad_format_type_id = aft.id
    AND clb.pricing_model_id = pm.id

    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

ORDER BY oc.id, aft.name
LIMIT 100
