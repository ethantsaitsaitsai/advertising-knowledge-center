"""
DataMergeProcessor

Merges MySQL and ClickHouse DataFrames using dynamic merge keys.
"""

import pandas as pd
from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class DataMergeProcessor(BaseProcessor):
    """
    Merge MySQL and ClickHouse data.

    This processor intelligently merges data from two sources:
    1. Determines optimal merge keys (cmpid vs cmpid + ad_format_type_id)
    2. Performs left join (MySQL as base)
    3. Fills NaN values appropriately (numeric → 0, text → "")
    4. Consolidates campaign_name (MySQL priority)

    Input:
        - context.df_mysql: Standardized MySQL DataFrame
        - context.df_clickhouse: Standardized ClickHouse DataFrame (may be empty)

    Output:
        - context.df_merged: Merged DataFrame

    Merge Strategy:
        - Simple Key: ['cmpid'] - When ad_format_type_id not in both sources
        - Composite Key: ['cmpid', 'ad_format_type_id'] - When available in both

    Example:
        MySQL (3 rows):
        | cmpid | campaign_name | budget_sum | ad_format_type_id |
        |-------|---------------|------------|-------------------|
        | 123   | Campaign A    | 10000      | 1                 |
        | 123   | Campaign A    | 15000      | 2                 |
        | 456   | Campaign B    | 20000      | 1                 |

        ClickHouse (2 rows):
        | cmpid | ad_format_type_id | impression | click |
        |-------|-------------------|------------|-------|
        | 123   | 1                 | 5000       | 100   |
        | 123   | 2                 | 3000       | 50    |

        Merged (3 rows):
        | cmpid | campaign_name | budget_sum | ad_format_type_id | impression | click |
        |-------|---------------|------------|-------------------|------------|-------|
        | 123   | Campaign A    | 10000      | 1                 | 5000       | 100   |
        | 123   | Campaign A    | 15000      | 2                 | 3000       | 50    |
        | 456   | Campaign B    | 20000      | 1                 | 0          | 0     |
    """

    def __init__(self):
        super().__init__(name="DataMergeProcessor")

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Merge MySQL and ClickHouse data.

        Args:
            context: Processing context

        Returns:
            Updated context with merged DataFrame
        """
        df_mysql = context.df_mysql
        df_ch = context.df_clickhouse

        # 1. Determine Merge Keys (Phase 4: Use FusionStrategy)
        strategy = context.metadata.get('fusion_strategy')
        if strategy is not None:
            # Use strategy decision
            merge_on = strategy.merge_keys
            context.add_debug_log(f"Merge keys from strategy: {merge_on}")
        else:
            # Fallback: Rule-based decision (backward compatible)
            merge_on = ['cmpid']
            if (not df_ch.empty and
                    'ad_format_type_id' in df_ch.columns and
                    'ad_format_type_id' in df_mysql.columns):
                merge_on.append('ad_format_type_id')
                context.add_debug_log("Using Composite Merge Key: ['cmpid', 'ad_format_type_id']")
            else:
                context.add_debug_log("Using Simple Merge Key: ['cmpid']")

        # 2. Perform Merge
        if not df_ch.empty:
            merged_df = pd.merge(df_mysql, df_ch, on=merge_on, how='left', suffixes=('', '_ch'))
        else:
            merged_df = df_mysql

        # 3. Smart Fillna (Don't fill dates with 0)
        # Fill numeric columns with 0
        num_cols = merged_df.select_dtypes(include=['number']).columns
        merged_df[num_cols] = merged_df[num_cols].fillna(0)

        # Fill object columns with empty string
        obj_cols = merged_df.select_dtypes(include=['object']).columns
        merged_df[obj_cols] = merged_df[obj_cols].fillna("")

        # 4. Consolidate Campaign Name
        # Priority: MySQL (campaign_name) > ClickHouse (campaign_name_ch)
        name_cols_ch = [c for c in merged_df.columns if 'campaign_name' in c and c != 'campaign_name']

        if 'campaign_name' in merged_df.columns:
            # Coalesce: Use MySQL name, fallback to ClickHouse name if MySQL is empty
            for other_col in name_cols_ch:
                merged_df['campaign_name'] = merged_df['campaign_name'].combine_first(
                    merged_df[other_col]
                )

        # 5. Store budget total for validation
        budget_col_merge = next((c for c in merged_df.columns if 'budget' in c), None)
        if budget_col_merge:
            merge_budget_total = merged_df[budget_col_merge].sum()
            context.metadata['merge_budget_total'] = merge_budget_total
            context.add_debug_log(f"Post-Merge Budget Total: {merge_budget_total:,.0f}")

        context.add_debug_log(f"Merged Cols: {list(merged_df.columns)}")

        # Update context
        context.df_merged = merged_df

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - merging is mandatory."""
        return True
