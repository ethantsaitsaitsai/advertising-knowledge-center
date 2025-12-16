"""
BudgetValidator

Validates budget consistency across different processing stages.
This helps detect data duplication bugs (e.g., Cartesian products, incorrect GROUP BY).
"""

from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class BudgetValidator(BaseProcessor):
    """
    Validate budget consistency across processing stages.

    This validator compares budget totals from three stages:
    1. **Raw SQL**: Budget from original MySQL query
    2. **Post-Merge**: Budget after MySQL + ClickHouse merge
    3. **Post-Aggregation**: Budget after re-aggregation by dimensions

    If the difference exceeds tolerance, a warning is generated.

    Input:
        - context.metadata['raw_budget_total']: Budget from raw MySQL data
        - context.metadata['merge_budget_total']: Budget after merge
        - context.metadata['agg_budget_total']: Budget after aggregation
        - context.state: Contains query_level for tolerance calculation

    Output:
        - context.warnings: Budget consistency warnings (if any)

    Tolerance Rules:
        - Default: 5% difference allowed
        - Execution + Ad Format: 10% allowed (due to floating point rounding)

    Example Warning:
        ⚠️ Budget Consistency Warning:
           Query Level: audience
           Raw SQL Total: 10,000
           Post-Merge Total: 10,000
           Post-Agg Total: 20,000
           Difference: 100.0% (Tolerance: 5%)
           Possible causes: SQL duplication, incorrect GROUP BY, or Cartesian product

    Common Causes of Budget Duplication:
        - **Segment Duplication**: One campaign has multiple segments
          → Solution: PreAggregationProcessor (MAX aggregation for budget)
        - **Ad Format Cartesian Product**: JOIN creates duplicate rows
          → Solution: Correct merge keys in DataMergeProcessor
        - **Incorrect GROUP BY**: Re-aggregation sums duplicates
          → Solution: Review AggregationProcessor group_cols
    """

    def __init__(self):
        super().__init__(name="BudgetValidator")

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Validate budget consistency.

        Args:
            context: Processing context

        Returns:
            Updated context with warnings (if any)
        """
        # Get budget totals from metadata
        raw_budget_total = context.metadata.get('raw_budget_total', 0)
        merge_budget_total = context.metadata.get('merge_budget_total', 0)
        agg_budget_total = context.metadata.get('agg_budget_total', 0)

        # Only validate if we have budget data
        if raw_budget_total <= 0 or agg_budget_total <= 0:
            context.add_debug_log("Skipping budget validation (no budget data)")
            return context

        # Calculate difference
        budget_diff_pct = abs(agg_budget_total - raw_budget_total) / raw_budget_total * 100

        # Determine tolerance based on query level and granularity
        tolerance = 5  # Default 5%
        query_level = context.state.get('query_level', 'strategy')

        # Higher tolerance for format-level queries (floating point rounding)
        if query_level == 'execution' and 'ad_format_type_id' in context.df_final.columns:
            tolerance = 10

        # Check if difference exceeds tolerance
        if budget_diff_pct > tolerance:
            warning = (
                f"⚠️ Budget Consistency Warning:\n"
                f"   Query Level: {query_level}\n"
                f"   Raw SQL Total: {raw_budget_total:,.0f}\n"
                f"   Post-Merge Total: {merge_budget_total:,.0f}\n"
                f"   Post-Agg Total: {agg_budget_total:,.0f}\n"
                f"   Difference: {budget_diff_pct:.1f}% (Tolerance: {tolerance}%)\n"
                f"   Possible causes: SQL duplication, incorrect GROUP BY, or Cartesian product"
            )
            context.warnings.append(warning)
            context.add_debug_log(warning)
        else:
            context.add_debug_log(
                f"✅ Budget Consistency Check PASSED: Diff {budget_diff_pct:.2f}% < {tolerance}%"
            )

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Execute if budget data is available.

        Skip validation if:
        - No budget columns exist
        - Budget totals are 0 or missing
        """
        raw_budget_total = context.metadata.get('raw_budget_total', 0)
        agg_budget_total = context.metadata.get('agg_budget_total', 0)

        return raw_budget_total > 0 and agg_budget_total > 0
