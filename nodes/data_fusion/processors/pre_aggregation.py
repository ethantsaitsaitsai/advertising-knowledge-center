"""
PreAggregationProcessor

Handles Segment deduplication for Audience-level queries.
This processor prevents budget duplication when multiple segments belong to the same campaign.
"""

import pandas as pd
from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class PreAggregationProcessor(BaseProcessor):
    """
    Pre-aggregate data when Segment columns exist.

    This processor solves a critical data duplication issue in Audience queries:
    - MySQL returns one row per segment (same campaign may have multiple segments)
    - Without aggregation, budget gets counted multiple times
    - This processor groups by campaign/ad_format and joins segment names

    Input:
        - context.df_mysql: MySQL DataFrame with potential segment column

    Output:
        - context.df_mysql: Aggregated DataFrame with deduplicated budgets

    Example Problem:
        Query: "2025年悠遊卡的進單金額 by Segment Category"
        MySQL返回 (Before Pre-Agg):
        | cmpid | budget_sum | segment_category    |
        |-------|------------|---------------------|
        | 123   | 10000      | 興趣-旅遊           |
        | 123   | 10000      | 興趣-美食           |  ← Budget duplicated!
        Total Budget: 20000 ❌ (should be 10000)

        After Pre-Agg:
        | cmpid | budget_sum | segment_category           |
        |-------|------------|----------------------------|
        | 123   | 10000      | 興趣-旅遊; 興趣-美食       |
        Total Budget: 10000 ✅

    Aggregation Strategy:
        - Segment column: Join unique values with '; '
        - Budget columns: MAX (prevents duplication)
        - Other numeric: MEAN
        - Text columns: FIRST

    Dependencies:
        - config.get_segment_column_candidates()
        - config.get_exclude_keywords()
    """

    def __init__(self, config):
        super().__init__(name="PreAggregationProcessor")
        self.config = config

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Pre-aggregate MySQL data if segment column exists.

        Args:
            context: Processing context

        Returns:
            Updated context with pre-aggregated df_mysql
        """
        df_mysql = context.df_mysql

        # 1. Find Segment Column
        seg_col_candidates = self.config.get_segment_column_candidates()
        seg_col = next((c for c in df_mysql.columns if c in seg_col_candidates), None)

        if not seg_col:
            # No segment column found, skip pre-aggregation
            context.add_debug_log("No Segment Column found. Skipping Pre-Aggregation.")
            return context

        context.add_debug_log(f"Found Segment Column: {seg_col}. Performing Pre-Aggregation.")

        # 2. Define Segment Join Function
        def join_unique_func(x):
            """Join unique non-null segment values with '; '."""
            return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))

        # 3. Build Group Keys (all non-numeric columns except segment)
        exclude_keywords = self.config.get_exclude_keywords()
        group_keys = []

        # Always include ID columns
        if 'cmpid' in df_mysql.columns:
            group_keys.append('cmpid')
        if 'ad_format_type_id' in df_mysql.columns:
            group_keys.append('ad_format_type_id')

        # Add other non-numeric columns (except segment and excluded keywords)
        for col in df_mysql.columns:
            if col in group_keys:  # Already added
                continue
            if col == seg_col:  # Skip segment (we'll aggregate it)
                continue
            if pd.api.types.is_numeric_dtype(df_mysql[col]):  # Skip numeric
                continue
            if any(k in col.lower() for k in exclude_keywords):  # Skip excluded
                continue
            group_keys.append(col)

        context.add_debug_log(f"Pre-Agg Group Keys: {group_keys}")

        # 4. Build Aggregation Dictionary
        agg_dict_pre = {}
        agg_dict_pre[seg_col] = join_unique_func

        for col in df_mysql.columns:
            if col in group_keys or col == seg_col:
                continue

            # CRITICAL FIX: Budget uses MAX to prevent duplication
            if 'budget' in col.lower():
                agg_dict_pre[col] = 'max'
            elif pd.api.types.is_numeric_dtype(df_mysql[col]):
                agg_dict_pre[col] = 'mean'
            else:
                agg_dict_pre[col] = 'first'

        # 5. Perform Aggregation
        # CRITICAL FIX: dropna=False keeps rows where ad_format_type_id is NULL
        df_mysql = df_mysql.groupby(group_keys, as_index=False, dropna=False).agg(agg_dict_pre)

        context.add_debug_log(f"Pre-Aggregation completed. Rows: {len(df_mysql)}")

        # Update context
        context.df_mysql = df_mysql

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Execute only if segment column exists.

        This processor is only needed for Audience-level queries that have
        segment data.
        """
        if context.df_mysql is None or context.df_mysql.empty:
            return False

        # Check if segment column exists
        seg_col_candidates = self.config.get_segment_column_candidates()
        seg_col = next((c for c in context.df_mysql.columns if c in seg_col_candidates), None)

        return seg_col is not None
