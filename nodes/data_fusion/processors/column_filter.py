"""
ColumnFilterProcessor

Filters DataFrame columns based on user's requested dimensions and metrics.
This processor runs AFTER aggregation to remove unwanted enriched columns.
"""

from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class ColumnFilterProcessor(BaseProcessor):
    """
    Filter columns to match user's original request.

    This processor is CRITICAL for removing columns added by enrichment processes
    (e.g., PerformanceGenerator adds 'cmpid', 'campaign_name' automatically,
    but user may not want them displayed).

    Input:
        - context.df_final: DataFrame after aggregation
        - context.metadata['user_original_dims']: Original user dimensions
        - context.metadata['user_original_metrics']: Original user metrics
        - context.metadata['group_cols']: Columns used for aggregation

    Output:
        - context.df_final: DataFrame with filtered columns

    Column Selection Priority:
        1. **Group Columns** (user's dimensions)
        2. **Segment Column** (if exists)
        3. **User-Requested Metrics** (exact match or keyword match)
        4. **KPIs** (CTR, VTR, ER - always include if they exist)
        5. **Fundamental Columns** (campaign_name, dates, budget - for context)

    Metric Mapping:
        User may request metrics using different names:
        - 'Budget_Sum' → matches 'budget' or 'budget_sum'
        - 'Impression_Sum' → matches 'impression' or 'total_impressions'
        - 'Click_Sum' → matches 'click' or 'total_clicks'

    Example:
        User Query: "各代理商的預算總額"
        - Original Dims: ['Agency']
        - Original Metrics: ['Budget_Sum']
        - Enriched by PerformanceGenerator: adds 'cmpid', 'campaign_name', 'CTR', 'VTR', 'ER'

        Before Filtering:
        | agency  | cmpid | campaign_name | budget_sum | ctr | vtr | er |
        |---------|-------|---------------|------------|-----|-----|-----|
        | Agency1 | 123   | Campaign A    | 10000      | 2.5 | 1.2 | 0.8 |

        After Filtering:
        | campaign_name | agency  | budget_sum | ctr | vtr | er |
        |---------------|---------|------------|-----|-----|-----|
        | Campaign A    | Agency1 | 10000      | 2.5 | 1.2 | 0.8 |

        Note: campaign_name kept for context, KPIs kept because they exist
    """

    def __init__(self, config):
        super().__init__(name="ColumnFilterProcessor")
        self.config = config

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Filter columns based on user's original request.

        Args:
            context: Processing context

        Returns:
            Updated context with filtered DataFrame
        """
        final_df = context.df_final

        # Get metadata
        user_original_metrics = context.metadata.get('user_original_metrics', [])
        group_cols = context.metadata.get('group_cols', [])

        # Get segment column
        seg_col_candidates = self.config.get_segment_column_candidates()
        seg_col = next((c for c in final_df.columns if c in seg_col_candidates), None)

        # 1. Start with group columns (user's dimensions)
        cols_to_keep = []
        for dim in group_cols:
            if dim in final_df.columns:
                cols_to_keep.append(dim)

        # 2. Add segment column if exists
        if seg_col and seg_col in final_df.columns and seg_col not in cols_to_keep:
            cols_to_keep.append(seg_col)

        # 3. Add user-requested metrics
        requested_metrics = [m.lower() for m in user_original_metrics]

        metric_map = {
            'budget_sum': ['budget', 'budget_sum'],
            'impression_sum': ['impression', 'total_impressions'],
            'click_sum': ['click', 'total_clicks'],
            'view3s_sum': ['view3s', 'views_3s'],
            'q100_sum': ['q100', 'views_100']
        }

        for req_m in requested_metrics:
            candidates = metric_map.get(req_m, [req_m])
            for cand in candidates:
                match = next((c for c in final_df.columns if cand in c), None)
                if match and match not in cols_to_keep:
                    cols_to_keep.append(match)

        # 4. Always add KPIs if they exist
        for kpi in ['ctr', 'vtr', 'er']:
            if kpi in final_df.columns and kpi not in cols_to_keep:
                cols_to_keep.append(kpi)

        # 5. Always include fundamental identification columns
        # Campaign Name - Essential for identifying campaigns
        if 'campaign_name' in final_df.columns and 'campaign_name' not in cols_to_keep:
            cols_to_keep.insert(0, 'campaign_name')

        # Start/End Date - Provides timeline context
        for date_col in ['start_date', 'end_date']:
            if date_col in final_df.columns and date_col not in cols_to_keep:
                cols_to_keep.append(date_col)

        # Budget - Fundamental financial data
        budget_col_match = next((c for c in final_df.columns if 'budget' in c), None)
        if budget_col_match and budget_col_match not in cols_to_keep:
            cols_to_keep.append(budget_col_match)

        # 6. Fallback: Add budget and impressions if only group columns selected
        if len(cols_to_keep) == len(group_cols):
            match = next((c for c in final_df.columns if 'budget' in c), None)
            if match and match not in cols_to_keep:
                cols_to_keep.append(match)

            # Find impression column
            imp_col_keywords = self.config.get_metric_keywords('impressions')
            imp_col = None
            for keyword in imp_col_keywords:
                match = next((c for c in final_df.columns if keyword.lower() in c), None)
                if match:
                    imp_col = match
                    break

            if imp_col and imp_col not in cols_to_keep:
                cols_to_keep.append(imp_col)

        context.add_debug_log(f"Cols to Keep: {cols_to_keep}")

        # Apply column filter
        if cols_to_keep:
            final_df = final_df[cols_to_keep]

        # Update context
        context.df_final = final_df

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - column filtering is mandatory."""
        return True
