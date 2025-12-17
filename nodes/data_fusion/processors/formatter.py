"""
FormattingProcessor

Final formatting stage: column reordering, row filtering, display name mapping.
This is the last processor before converting to output format.
"""

import pandas as pd
from typing import Optional
from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class FormattingProcessor(BaseProcessor):
    """
    Final formatting and cleanup of the DataFrame.

    This processor performs multiple formatting operations:
    1. Budget column formatting (convert to integers)
    2. Hide technical ID columns (cmpid, ad_format_type_id, etc.)
    3. Column reordering (Campaign Name -> Format -> Segment -> Metrics)
    4. Generate budget note based on query_level
    5. Filter invalid campaign names (e.g., '0')
    6. Filter rows with invalid Ad Format (if user requested it)
    7. Filter rows with empty Agency/Advertiser
    8. Hide all-zero default metrics
    9. Rename columns to display format (lowercase → Display_Name)

    Input:
        - context.df_final: DataFrame after aggregation and KPI calculation
        - context.metadata['user_original_dims']: Original user dimensions
        - context.metadata['user_original_metrics']: Original user metrics

    Output:
        - context.df_final: Formatted DataFrame ready for output
        - context.metadata['budget_note']: Explanation of budget type

    Dependencies:
        - Requires config for hidden_columns, display_order, valid_dimensions
        - Requires user_original_dims and user_original_metrics from IntentExtraction
    """

    def __init__(self, config):
        super().__init__(name="FormattingProcessor")
        self.config = config

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Format the final DataFrame for display.

        Args:
            context: Processing context

        Returns:
            Updated context with formatted DataFrame
        """
        final_df = context.df_final
        state = context.state

        # Get user's original intent
        user_original_dims = context.metadata.get('user_original_dims', [])
        user_original_metrics = context.metadata.get('user_original_metrics', [])
        context.add_debug_log(f"FormattingProcessor: User Original Metrics: {user_original_metrics}")

        # 1. Budget Formatting
        for col in final_df.columns:
            if 'budget' in col and pd.api.types.is_numeric_dtype(final_df[col]):
                final_df[col] = final_df[col].fillna(0).astype(int)

        # 2. Identify key columns
        camp_name_col = next((c for c in final_df.columns if c == 'campaign_name'), None)
        start_col = next((c for c in final_df.columns if c == 'start_date'), None)
        end_col = next((c for c in final_df.columns if c == 'end_date'), None)

        context.add_debug_log("Keeping start_date and end_date as separate columns")

        # 3. Hide Technical IDs
        cols_to_hide = list(self.config.get_hidden_columns())
        final_df = final_df.drop(
            columns=[c for c in final_df.columns if c.lower() in cols_to_hide],
            errors='ignore'
        )

        # 4. Reorder Columns
        preferred_order = self.config.get_display_order()
        new_cols = []

        # Add preferred columns if they exist
        for p_col in preferred_order:
            match = next((c for c in final_df.columns if c.lower() == p_col.lower()), None)
            if match:
                new_cols.append(match)

        # Add remaining columns
        for col in final_df.columns:
            if col not in new_cols:
                new_cols.append(col)

        final_df = final_df[new_cols]

        # 5. Generate Budget Note
        query_level = state.get("query_level", "strategy")
        budget_note = ""
        if query_level == "contract":
            budget_note = "這是合約層級的進單金額 (Booking Amount)，不包含執行細節。"
        elif query_level in ["execution", "strategy", "audience"]:
            budget_note = "這是系統設定的執行預算上限 (Execution Budget)。"

        context.metadata['budget_note'] = budget_note

        # 6. Filter Invalid Campaign Names
        if camp_name_col and camp_name_col in final_df.columns:
            final_df = final_df[final_df[camp_name_col].astype(str) != '0']

        # 7. Ad Format Filtering (Phase 4: Use FusionStrategy)
        ad_format_col = next(
            (c for c in final_df.columns if 'ad_format' in c and c != 'ad_format_type_id'),
            None
        )

        # Get filter strategy
        strategy = context.metadata.get('fusion_strategy')
        if strategy is not None:
            filter_ad_format = strategy.filter_ad_format
            context.add_debug_log(f"Ad Format filter strategy from FusionPlanner: {filter_ad_format}")
        else:
            # Fallback: Rule-based decision
            user_requested_ad_format = 'ad_format' in [d.lower() for d in user_original_dims]
            user_requested_performance = any(
                m.lower() in ['ctr', 'vtr', 'er', 'impression', 'click']
                for m in user_original_metrics
            )

            if user_requested_ad_format:
                filter_ad_format = "strict" if user_requested_performance else "loose"
            else:
                filter_ad_format = "none"

        # Apply filtering based on strategy
        if ad_format_col and ad_format_col in final_df.columns:
            if filter_ad_format == "strict":
                # Strictly filter out rows without valid format
                initial_count = len(final_df)
                context.add_debug_log(
                    "Ad_Format filtering: STRICT (removing empty/null values)"
                )
                mask = ~final_df[ad_format_col].astype(str).str.strip().isin(
                    ['0', 'nan', 'none', '', 'None']
                )
                filtered_df = final_df[mask]
                dropped_count = initial_count - len(filtered_df)

                # Safety Check: Don't remove ALL data
                if dropped_count == initial_count and initial_count > 0:
                    context.add_debug_log(
                        f"Ad_Format filter would remove all {initial_count} rows. "
                        "Keeping data with empty Ad_Format."
                    )
                    final_df[ad_format_col] = final_df[ad_format_col].astype(str).replace(
                        ['0', 'nan', 'None'], ''
                    )
                else:
                    final_df = filtered_df
                    if dropped_count > 0:
                        context.add_debug_log(f"Dropped {dropped_count} rows with invalid Ad Format")

            elif filter_ad_format == "loose":
                # Keep empty/null (represents 'not set'), only filter '0'
                initial_count = len(final_df)
                context.add_debug_log("Ad_Format filtering: LOOSE (only filtering '0')")
                mask = ~final_df[ad_format_col].astype(str).str.strip().isin(['0'])
                filtered_df = final_df[mask]
                dropped_count = initial_count - len(filtered_df)

                if dropped_count > 0:
                    final_df = filtered_df
                    context.add_debug_log(f"Dropped {dropped_count} rows with '0' Ad Format")

            elif filter_ad_format == "none":
                # Don't filter rows, but drop the column if user didn't request it
                user_requested_ad_format = 'ad_format' in [d.lower() for d in user_original_dims]
                if not user_requested_ad_format:
                    context.add_debug_log(
                        f"Ad_Format filtering: NONE, dropping column '{ad_format_col}'"
                    )
                    final_df = final_df.drop(columns=[ad_format_col], errors='ignore')

        # 8. Filter Empty Agency
        agency_col = next((c for c in final_df.columns if c == 'agency'), None)
        if agency_col and agency_col in final_df.columns:
            final_df = final_df[~final_df[agency_col].astype(str).isin(['None', 'nan', ''])]
            final_df = final_df[final_df[agency_col].notna()]

        # 9. Filter Empty Advertiser
        adv_col = next((c for c in final_df.columns if c == 'advertiser'), None)
        if adv_col and adv_col in final_df.columns:
            final_df = final_df[~final_df[adv_col].astype(str).isin(['None', 'nan', ''])]
            final_df = final_df[final_df[adv_col].notna()]

        # 10. Hide All-Zero Metrics (Phase 4: Use FusionStrategy)
        was_default = state.get("was_default_metrics", False)

        # Get hide strategy
        if strategy is not None:
            hide_zero_metrics = strategy.hide_zero_metrics
            context.add_debug_log(f"Hide zero metrics strategy from FusionPlanner: {hide_zero_metrics}")
        else:
            # Fallback: Always hide by default
            hide_zero_metrics = True

        # Only hide if strategy allows
        if hide_zero_metrics:
            for metric in ['ctr', 'vtr', 'er']:
                if metric in final_df.columns:
                    # Clean user metrics for comparison
                    clean_user_metrics = [m.strip().upper() for m in user_original_metrics]
                    
                    user_requested_metric = metric.strip().upper() in clean_user_metrics

                    if (final_df[metric] == 0).all():
                        # Metric is all zeros
                        if user_requested_metric:
                            # User explicitly requested it → ALWAYS keep it (even if all zeros)
                            context.add_debug_log(
                                f"Keeping all-zero metric '{metric}' (user explicitly requested it)"
                            )
                        elif was_default:
                            # Default metric with all zeros and not requested → hide it
                            final_df = final_df.drop(columns=[metric])
                            context.add_debug_log(f"Hiding all-zero DEFAULT metric '{metric}'")
                        else:
                            # Not default, not requested, all zeros → hide it
                            final_df = final_df.drop(columns=[metric])
                            context.add_debug_log(f"Hiding all-zero metric '{metric}' (not requested)")
                    else:
                        # Metric has non-zero values → ALWAYS keep it (data exists)
                        if not user_requested_metric:
                            context.add_debug_log(
                                f"Keeping metric '{metric}' (has non-zero values, even though not explicitly requested)"
                            )

        # 11. Final Renaming (Restore Capitalization for Display)
        display_map = {}
        valid_dims_map = self.config.get_valid_dimensions()

        metric_display_map = {
            'ctr': 'CTR',
            'vtr': 'VTR',
            'er': 'ER',
            'budget_sum': 'Budget_Sum',
            'impression': 'Impression',
            'click': 'Click'
        }

        for col in final_df.columns:
            if col in valid_dims_map:
                display_map[col] = valid_dims_map[col]
            elif col in metric_display_map:
                display_map[col] = metric_display_map[col]
            # Ad-hoc fixes
            elif 'ad_format' in col and 'type' in col:
                display_map[col] = 'Ad_Format'
            elif 'segment' in col:
                display_map[col] = 'Segment_Category'

        if display_map:
            final_df.rename(columns=display_map, inplace=True)

        # Update context
        context.df_final = final_df

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - formatting is mandatory."""
        return True
