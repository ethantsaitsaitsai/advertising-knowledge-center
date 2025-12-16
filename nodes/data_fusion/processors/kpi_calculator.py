"""
KPICalculator

Calculates derived metrics (CTR, VTR, ER) from aggregated data.
"""

from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class KPICalculator(BaseProcessor):
    """
    Calculate derived KPI metrics.

    This processor computes performance metrics based on aggregated data:
    - CTR (Click-Through Rate) = Clicks / Impressions * 100
    - VTR (View-Through Rate) = Views (Q100) / Impressions * 100
    - ER (Engagement Rate) = Engagements / Impressions * 100

    The denominator prioritizes Effective Impressions over Total Impressions.

    Input:
        - context.df_final: DataFrame with aggregated metrics
        - Must contain impression/effective_impression column
        - May contain clicks, views_100 (q100), engagements columns

    Output:
        - context.df_final: DataFrame with added ctr/vtr/er columns (lowercase)

    Dependencies:
        - Requires config.get_metric_keywords() to find columns
        - Must run AFTER aggregation (needs summed metrics)

    Formulas (per domain_knowledge.md):
        - CTR = Total Clicks / Effective Impressions
        - VTR = SUM(q100) / Effective Impressions
        - ER = Total Engagements / Effective Impressions
    """

    def __init__(self, config):
        super().__init__(name="KPICalculator")
        self.config = config

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Calculate KPI metrics.

        Args:
            context: Processing context

        Returns:
            Updated context with KPI columns added
        """
        final_df = context.df_final

        # Build lowercase column mapping for case-insensitive lookup
        all_cols_lower = {c: c for c in final_df.columns}

        def find_col(metric_key: str):
            """Find column by metric key using config-defined keywords."""
            keywords = self.config.get_metric_keywords(metric_key)
            for k in keywords:
                if k.lower() in all_cols_lower:
                    return all_cols_lower[k.lower()]
            return None

        # Find metric columns
        imp_col = find_col('impressions')
        eff_imp_col = find_col('effective_impressions')
        click_col = find_col('clicks')
        view100_col = find_col('views_100')
        view3s_col = find_col('views_3s')
        eng_col = find_col('engagements')

        context.add_debug_log(
            f"Found imp_col: {imp_col}, eff_imp_col: {eff_imp_col}, "
            f"click_col: {click_col}, view100_col: {view100_col}, eng_col: {eng_col}"
        )

        # Denominator priority: Effective Impressions > Total Impressions
        denom_col = eff_imp_col if eff_imp_col else imp_col

        if denom_col:
            context.add_debug_log(f"Calculating KPIs using denominator: {denom_col}")

            # Calculate CTR
            if click_col:
                context.add_debug_log(f"Calculating CTR using {click_col} / {denom_col}")
                final_df['ctr'] = final_df.apply(
                    lambda x: (x[click_col] / x[denom_col] * 100) if x[denom_col] > 0 else 0,
                    axis=1
                ).round(2)

            # Calculate VTR (use Q100 per domain knowledge)
            if view100_col:
                context.add_debug_log(f"Calculating VTR using {view100_col} / {denom_col}")
                final_df['vtr'] = final_df.apply(
                    lambda x: (x[view100_col] / x[denom_col] * 100) if x[denom_col] > 0 else 0,
                    axis=1
                ).round(2)

            # Calculate ER
            if eng_col:
                context.add_debug_log(f"Calculating ER using {eng_col} / {denom_col}")
                final_df['er'] = final_df.apply(
                    lambda x: (x[eng_col] / x[denom_col] * 100) if x[denom_col] > 0 else 0,
                    axis=1
                ).round(2)
        else:
            context.add_debug_log("No impression column found. Skipping KPI calculation.")

        context.add_debug_log(f"Post-KPI Calc Columns: {list(final_df.columns)}")

        # Update context
        context.df_final = final_df

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Execute if we have impression data.

        KPI calculation only makes sense if we have impression metrics.
        """
        if context.df_final is None or context.df_final.empty:
            return False

        # Check if we have any impression column
        all_cols_lower = {c.lower(): c for c in context.df_final.columns}
        has_impressions = any(
            keyword in all_cols_lower
            for keyword in ['impression', 'effective_impressions', 'impressions']
        )

        return has_impressions
