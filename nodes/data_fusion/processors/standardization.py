"""
StandardizationProcessor

Standardizes column names and data types across MySQL and ClickHouse DataFrames.
This ensures consistent data representation for downstream processing.
"""

from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext
from nodes.data_fusion.utils.converters import NumericConverter


class StandardizationProcessor(BaseProcessor):
    """
    Standardize column names and data types.

    This processor performs three key transformations:
    1. Lowercase all column names (prevents 'CTR' vs 'ctr' issues)
    2. Normalize column names (e.g., 'id' → 'cmpid')
    3. Convert numeric columns to proper data types

    Input:
        - context.df_mysql: Raw MySQL DataFrame
        - context.df_clickhouse: Raw ClickHouse DataFrame

    Output:
        - context.df_mysql: Standardized MySQL DataFrame
        - context.df_clickhouse: Standardized ClickHouse DataFrame
    """

    def __init__(self):
        super().__init__(name="StandardizationProcessor")

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Standardize column names and data types.

        Args:
            context: Processing context

        Returns:
            Updated context with standardized DataFrames
        """
        # 1. Lowercase all column names
        context.df_mysql.columns = context.df_mysql.columns.str.lower()

        if not context.df_clickhouse.empty:
            context.df_clickhouse.columns = context.df_clickhouse.columns.str.lower()

        context.add_debug_log(f"Standardized columns: {list(context.df_mysql.columns)}")

        # 2. Normalize column names
        context.df_mysql = self._normalize_columns(context.df_mysql, "MySQL")

        if not context.df_clickhouse.empty:
            context.df_clickhouse = self._normalize_columns(context.df_clickhouse, "ClickHouse")

        # 3. Convert to numeric types
        context.df_mysql = NumericConverter.convert_dataframe(context.df_mysql, "MySQL")

        if not context.df_clickhouse.empty:
            context.df_clickhouse = NumericConverter.convert_dataframe(context.df_clickhouse, "ClickHouse")

        # 4. Ensure ID columns are numeric
        context.df_mysql = NumericConverter.ensure_numeric_ids(
            context.df_mysql,
            ['cmpid', 'id', 'ad_format_type_id']
        )

        if not context.df_clickhouse.empty:
            context.df_clickhouse = NumericConverter.ensure_numeric_ids(
                context.df_clickhouse,
                ['cmpid', 'ad_format_type_id']
            )

        # 5. Strip whitespace from text columns
        context.df_mysql = self._strip_text_columns(context.df_mysql)

        if not context.df_clickhouse.empty:
            context.df_clickhouse = self._strip_text_columns(context.df_clickhouse)

        # 6. Store raw budget total for validation
        budget_col = next((c for c in context.df_mysql.columns if 'budget' in c.lower()), None)
        if budget_col:
            raw_budget_total = context.df_mysql[budget_col].sum()
            context.metadata['raw_budget_total'] = raw_budget_total
            context.add_debug_log(f"Raw SQL Budget Total: {raw_budget_total:,.0f}")

        return context

    def _normalize_columns(self, df, source_name: str):
        """
        Normalize column names to standard format.

        Handles:
        - 'id' → 'cmpid' (if cmpid doesn't exist)
        - Standardize 'ad_format_type_id' variations

        Args:
            df: DataFrame to normalize
            source_name: "MySQL" or "ClickHouse" (for logging)

        Returns:
            DataFrame with normalized columns
        """
        rename_map = {}

        for col in df.columns:
            # Normalize 'id' to 'cmpid'
            if col == 'id' and 'cmpid' not in df.columns:
                rename_map[col] = 'cmpid'

            # Standardize ad_format_type_id
            elif 'ad_format_type_id' in col and col != 'ad_format_type_id':
                rename_map[col] = 'ad_format_type_id'

        if rename_map:
            df.rename(columns=rename_map, inplace=True)
            self.add_debug_log(f"{source_name} column normalization: {rename_map}")

        return df

    def _strip_text_columns(self, df):
        """
        Strip whitespace from text (object) columns.

        This prevents issues with groupby where 'Value' and 'Value ' are treated
        as different keys.

        Args:
            df: DataFrame to process

        Returns:
            DataFrame with stripped text columns
        """
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()

        return df

    def add_debug_log(self, message: str):
        """Helper to add debug logs (temporary, will be removed once integrated into context)."""
        print(f"DEBUG [{self.name}] {message}")

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - standardization is mandatory."""
        return True
