"""
DataRetrievalProcessor

Extracts MySQL and ClickHouse data from the AgentState.
This is the first stage of the DataFusion pipeline.
"""

import pandas as pd
from typing import Optional
from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class DataRetrievalProcessor(BaseProcessor):
    """
    Extract MySQL and ClickHouse data from AgentState.

    This processor retrieves raw data from two sources:
    1. MySQL data (from CampaignAgent) - Primary source
    2. ClickHouse data (from PerformanceAgent) - Optional supplement

    Input:
        - context.state: AgentState with sql_result, campaign_data, clickhouse_result

    Output:
        - context.df_mysql: MySQL data as DataFrame
        - context.df_clickhouse: ClickHouse data as DataFrame (if available)

    Raises:
        ValueError: If MySQL data is missing or invalid
    """

    def __init__(self):
        super().__init__(name="DataRetrievalProcessor")

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Extract data from state and convert to DataFrames.

        Args:
            context: Processing context

        Returns:
            Updated context with df_mysql and df_clickhouse populated

        Raises:
            ValueError: If MySQL data or columns are missing
        """
        state = context.state

        # 1. Extract MySQL data
        mysql_data = state.get('sql_result')
        sql_result_columns = state.get('sql_result_columns')

        # Fallback to campaign_data (Single Path Execution)
        if not mysql_data:
            campaign_data = state.get('campaign_data')
            if campaign_data:
                mysql_data = campaign_data.get('data')
                sql_result_columns = campaign_data.get('columns')

        # Validate MySQL data
        if not mysql_data or not sql_result_columns:
            raise ValueError("查無數據 (MySQL 無回傳)。")

        # Convert to DataFrame
        context.df_mysql = pd.DataFrame(mysql_data, columns=sql_result_columns)
        context.add_debug_log(f"MySQL data retrieved: {len(context.df_mysql)} rows, "
                             f"{len(sql_result_columns)} columns")

        # 2. Extract ClickHouse data (optional)
        ch_data = state.get('clickhouse_result', [])
        if ch_data:
            context.df_clickhouse = pd.DataFrame(ch_data)
            context.add_debug_log(f"ClickHouse data retrieved: {len(context.df_clickhouse)} rows")
        else:
            context.df_clickhouse = pd.DataFrame()  # Empty DataFrame
            context.add_debug_log("No ClickHouse data available")

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - data retrieval is mandatory."""
        return True
