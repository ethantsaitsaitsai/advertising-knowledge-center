"""
AggregationProcessor

Main aggregation stage: Groups data by user-requested dimensions.
"""

import pandas as pd
from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class AggregationProcessor(BaseProcessor):
    """
    Aggregate merged data by user dimensions.

    This processor performs the main data aggregation based on user's requested
    dimensions. It handles two modes:
    - **Total Mode**: No dimensions → aggregate everything to a single row
    - **Dimension Mode**: Group by dimensions → one row per unique combination

    Input:
        - context.df_merged: Merged MySQL + ClickHouse DataFrame
        - context.metadata['user_original_dims']: User's requested dimensions
        - context.state: Contains query_level

    Output:
        - context.df_final: Aggregated DataFrame ready for KPI calculation

    Grouping Strategy:
        1. Map user dimensions to actual column names using intent_to_alias
        2. Auto-add campaign_name for campaign-level queries (strategy/execution/audience)
        3. Exclude ID and date columns from aggregation
        4. Determine which columns to SUM vs JOIN

    Aggregation Rules:
        - Numeric columns: SUM
        - Budget/sum columns: SUM (forced, even if type detection fails)
        - Date columns (start_date, end_date): MAX
        - Segment columns: JOIN UNIQUE with '; '

    Example (Total Mode):
        Input (merged_df):
        | cmpid | campaign_name | budget_sum | impressions |
        |-------|---------------|------------|-------------|
        | 123   | Campaign A    | 10000      | 5000        |
        | 456   | Campaign B    | 20000      | 8000        |

        Output (final_df):
        | Item  | budget_sum | impressions |
        |-------|------------|-------------|
        | Total | 30000      | 13000       |

    Example (Dimension Mode - Group by Agency):
        User Dimensions: ['Agency']
        Input (merged_df):
        | cmpid | campaign_name | agency  | budget_sum | impressions |
        |-------|---------------|---------|------------|-------------|
        | 123   | Campaign A    | Agency1 | 10000      | 5000        |
        | 456   | Campaign B    | Agency1 | 20000      | 8000        |
        | 789   | Campaign C    | Agency2 | 15000      | 6000        |

        Output (final_df):
        | agency  | budget_sum | impressions |
        |---------|------------|-------------|
        | Agency1 | 30000      | 13000       |
        | Agency2 | 15000      | 6000        |

    Dependencies:
        - config.get_intent_to_alias_map()
        - Requires user_original_dims from IntentExtraction
    """

    def __init__(self, config):
        super().__init__(name="AggregationProcessor")
        self.config = config

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Aggregate merged data.

        Args:
            context: Processing context

        Returns:
            Updated context with aggregated DataFrame
        """
        merged_df = context.df_merged
        state = context.state

        # Get user's original dimensions
        user_original_dims = context.metadata.get('user_original_dims', [])
        context.add_debug_log(f"User Original Dimensions (for grouping): {user_original_dims}")

        # 1. Build Group Columns
        intent_to_alias = self.config.get_intent_to_alias_map()
        group_cols = []
        col_lower_map = {c: c for c in merged_df.columns}
        concat_cols = []

        for d in user_original_dims:
            target_aliases = intent_to_alias.get(d, [d])
            if not isinstance(target_aliases, list):
                target_aliases = [target_aliases]

            found_col = None
            for alias in target_aliases:
                if alias.lower() in col_lower_map:
                    found_col = col_lower_map[alias.lower()]
                    break

            if found_col and found_col not in group_cols:
                group_cols.append(found_col)

        # 2. Auto-add campaign_name for campaign-level queries
        query_level = state.get('query_level', 'strategy')
        if query_level in ['strategy', 'audience', 'execution']:
            if 'campaign_name' in merged_df.columns and 'campaign_name' not in group_cols:
                group_cols.insert(0, 'campaign_name')
                context.add_debug_log(
                    f"Auto-added campaign_name to group_cols for {query_level} level query"
                )

        context.add_debug_log(f"Final Group Cols: {group_cols}")

        # 3. Identify Numeric Columns to Aggregate
        exclude_cols_lower = {'cmpid', 'id', 'start_date', 'end_date', 'schedule_dates'}
        for gc in group_cols:
            exclude_cols_lower.add(gc)

        numeric_cols = [
            c for c in merged_df.columns
            if pd.api.types.is_numeric_dtype(merged_df[c]) and c not in exclude_cols_lower
        ]

        context.add_debug_log(f"Numeric Cols: {numeric_cols}")

        # 4. Identify Concat Columns (e.g., segment)
        # Get segment column from metadata if it was found in pre-aggregation
        seg_col_candidates = self.config.get_segment_column_candidates()
        seg_col = next((c for c in merged_df.columns if c in seg_col_candidates), None)

        if seg_col and seg_col not in group_cols and seg_col in merged_df.columns:
            concat_cols.append(seg_col)

        # 5. Perform Aggregation
        if not group_cols:
            # Case A: Total Aggregation (no dimensions)
            if not numeric_cols and not concat_cols:
                final_df = merged_df
            else:
                # Sum numeric columns
                if numeric_cols:
                    numeric_res = merged_df[numeric_cols].sum()
                else:
                    numeric_res = pd.Series(dtype='float64')

                # Join concat columns
                def join_unique(x):
                    return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))

                if concat_cols:
                    text_res = merged_df[concat_cols].apply(join_unique)
                else:
                    text_res = pd.Series(dtype='object')

                final_series = pd.concat([numeric_res, text_res])
                final_df = final_series.to_frame().T
                final_df['Item'] = 'Total'
        else:
            # Case B: Group By Dimensions
            agg_dict = {col: 'sum' for col in numeric_cols}

            # Force SUM for budget/sum columns (even if type detection fails)
            for col in merged_df.columns:
                col_lower = col  # already lowercase
                if 'budget' in col_lower or 'sum' in col_lower:
                    if col not in group_cols and col not in agg_dict:
                        # Try to convert to numeric
                        merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
                        agg_dict[col] = 'sum'

            # Preserve Date Columns
            for date_col in ['start_date', 'end_date']:
                if date_col in merged_df.columns and date_col not in group_cols:
                    agg_dict[date_col] = 'max'

            # Join unique for concat columns
            def join_unique(x):
                return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))

            for c in concat_cols:
                agg_dict[c] = join_unique

            # Perform aggregation
            if not agg_dict:
                final_df = merged_df[group_cols].drop_duplicates().reset_index(drop=True)
            else:
                final_df = merged_df.groupby(group_cols, dropna=False).agg(agg_dict).reset_index()

        # 6. Store budget total for validation
        budget_col_agg = next((c for c in final_df.columns if 'budget' in c), None)
        if budget_col_agg:
            agg_budget_total = final_df[budget_col_agg].sum()
            context.metadata['agg_budget_total'] = agg_budget_total
            context.add_debug_log(f"Post-Agg Budget Total: {agg_budget_total:,.0f}")

        # Update context
        context.df_final = final_df

        # Store group_cols and user_original_analysis_needs for downstream processors
        context.metadata['group_cols'] = group_cols

        # Store user_original_analysis_needs for downstream processors
        user_intent = state.get('user_intent')
        if user_intent and user_intent.analysis_needs:
            raw_analysis_needs = user_intent.analysis_needs
        else:
            raw_analysis_needs = state.get('analysis_needs')

        if hasattr(raw_analysis_needs, 'model_dump'):
            context.metadata['user_original_analysis_needs'] = raw_analysis_needs.model_dump()
        elif hasattr(raw_analysis_needs, 'dict'):
            context.metadata['user_original_analysis_needs'] = raw_analysis_needs.dict()
        elif isinstance(raw_analysis_needs, dict):
            context.metadata['user_original_analysis_needs'] = raw_analysis_needs
        else:
            context.metadata['user_original_analysis_needs'] = {}

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - aggregation is mandatory."""
        return True
