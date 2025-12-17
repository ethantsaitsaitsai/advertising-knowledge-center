"""
Data Type Converters

Utility functions for converting data types in DataFrames.
"""

import pandas as pd
from typing import List


class NumericConverter:
    """
    Utility for safe numeric conversion of DataFrame columns.

    This class provides methods to intelligently convert columns to numeric types,
    handling common issues like comma-separated numbers and mixed data types.
    """

    # Columns that should NOT be converted to numeric (IDs)
    EXCLUDE_COLUMNS = ['cmpid', 'id', 'ad_format_type_id', 'ad_format', 'segment_category']

    # Keywords that indicate a column likely contains metrics
    METRIC_KEYWORDS = ['budget', 'sum', 'price', 'count', 'impression', 'click', 'view']

    @classmethod
    def convert_dataframe(cls, df: pd.DataFrame, name: str = "df") -> pd.DataFrame:
        """
        Safely convert numeric columns in a DataFrame.

        This method attempts to convert each column to numeric type, with special
        handling for metric columns (removing commas, forcing conversion).

        Args:
            df: DataFrame to process
            name: Name for debug logging (e.g., "MySQL", "ClickHouse")

        Returns:
            DataFrame with converted columns
        """
        for col in df.columns:
            # Skip ID columns
            if col in cls.EXCLUDE_COLUMNS:
                continue

            # Check if this is likely a metric column
            is_metric_candidate = any(k in col for k in cls.METRIC_KEYWORDS)

            if is_metric_candidate:
                # Remove comma separators from numbers (e.g., "1,000" → "1000")
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.replace(',', '', regex=False)

            # Attempt numeric conversion
            converted = pd.to_numeric(df[col], errors='coerce')

            # Decide whether to keep the conversion
            # If all values became NaN but original had data, it's likely a text column
            # Exception: For metric candidates, prefer numeric NaN over incorrect text
            if converted.isna().all() and df[col].notna().any() and not is_metric_candidate:
                # Keep original (likely text column)
                continue

            # Apply conversion
            df[col] = converted

        return df

    @classmethod
    def ensure_numeric_ids(cls, df: pd.DataFrame, id_columns: List[str]) -> pd.DataFrame:
        """
        Ensure specified ID columns are numeric.

        Args:
            df: DataFrame to process
            id_columns: List of column names that should be numeric IDs

        Returns:
            DataFrame with numeric ID columns
        """
        for col in id_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df
