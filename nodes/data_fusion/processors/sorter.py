"""
SortingProcessor

Sorts and limits the final DataFrame based on calculation_type (Ranking vs Trend).
"""

from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class SortingProcessor(BaseProcessor):
    """
    Sort and limit DataFrame.

    This processor applies sorting and row limiting based on calculation_type:
    - **Ranking**: Sort by highest value metric (budget, impressions, etc.)
    - **Trend**: Sort by date/time ascending
    - **Total**: No sort (or auto-switch to Ranking if > 20 rows)

    Input:
        - context.df_final: DataFrame to sort
        - context.metadata['user_original_analysis_needs']: Contains calculation_type
        - context.state: Contains limit (default: 20)

    Output:
        - context.df_final: Sorted and limited DataFrame

    Auto-Ranking Logic:
        If calculation_type is 'Total' but the dataset has > 20 rows, automatically
        switch to 'Ranking' mode to show the top items by the most significant metric.

    Ranking Sort Priority:
        1. Budget (most common for business queries)
        2. (Future: Could prioritize impressions, clicks, etc. based on query context)

    Trend Sort Priority:
        1. Any column with 'date' or 'month' in the name
    """

    def __init__(self):
        super().__init__(name="SortingProcessor")

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Sort and limit the DataFrame.

        Args:
            context: Processing context

        Returns:
            Updated context with sorted DataFrame
        """
        final_df = context.df_final
        state = context.state

        # Get calculation type from user's original intent
        user_original_analysis_needs = context.metadata.get('user_original_analysis_needs', {})
        calc_type = user_original_analysis_needs.get('calculation_type', 'Total')

        # Smart Sorting: Auto-switch to Ranking for large datasets
        if len(final_df) > 20 and calc_type == 'Total':
            calc_type = 'Ranking'
            context.add_debug_log("Auto-switching to Ranking mode due to large dataset.")

        # Apply Sorting
        if calc_type == 'Ranking':
            sort_col = None

            # Strategy: Budget Fallback (most common business metric)
            if not sort_col:
                sort_col = next((c for c in final_df.columns if 'budget' in c), None)

            if sort_col:
                context.add_debug_log(f"Sorting by {sort_col} (Descending) for Ranking")
                final_df = final_df.sort_values(by=sort_col, ascending=False)

        elif calc_type == 'Trend':
            date_col = next((c for c in final_df.columns if 'date' in c or 'month' in c), None)
            if date_col:
                context.add_debug_log(f"Sorting by {date_col} (Ascending) for Trend")
                final_df = final_df.sort_values(by=date_col, ascending=True)

        # Apply Row Limit
        limit = state.get('limit') or 20
        total_rows = len(final_df)

        if total_rows > limit:
            context.add_debug_log(f"Applying Limit: Top {limit} of {total_rows}")
            final_df = final_df.head(limit)

        # Update context
        context.df_final = final_df

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - sorting/limiting is standard for display."""
        return True
