"""
Processing Context for DataFusion Pipeline

The ProcessingContext encapsulates all data and metadata that flows through
the processing pipeline. It serves as a shared state object that processors
can read from and write to.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from schemas.state import AgentState


class ProcessingContext:
    """
    Shared context object passed through the DataFusion pipeline.

    This class encapsulates all data (DataFrames) and metadata (configuration,
    debug logs, etc.) that flows through the processing stages.

    Attributes:
        state (AgentState): Original LangGraph state
        df_mysql (pd.DataFrame): MySQL data (from CampaignAgent)
        df_clickhouse (pd.DataFrame): ClickHouse data (from PerformanceAgent)
        df_merged (pd.DataFrame): Merged MySQL + ClickHouse data
        df_final (pd.DataFrame): Final processed dataframe ready for output
        metadata (Dict[str, Any]): Arbitrary metadata for processors
        debug_logs (List[str]): Debug messages for troubleshooting
        warnings (List[str]): Warning messages (e.g., budget inconsistency)
    """

    def __init__(self, state: AgentState):
        """
        Initialize ProcessingContext from LangGraph state.

        Args:
            state: The original AgentState from LangGraph
        """
        self.state = state

        # DataFrames at different processing stages
        self.df_mysql: Optional[pd.DataFrame] = None
        self.df_clickhouse: Optional[pd.DataFrame] = None
        self.df_merged: Optional[pd.DataFrame] = None
        self.df_final: Optional[pd.DataFrame] = None

        # Metadata storage
        self.metadata: Dict[str, Any] = {}

        # Logging
        self.debug_logs: List[str] = []
        self.warnings: List[str] = []

    def add_debug_log(self, message: str) -> None:
        """
        Add a debug log message.

        Args:
            message: Debug message to log
        """
        self.debug_logs.append(message)
        print(f"DEBUG [DataFusion] {message}")

    def add_warning(self, message: str) -> None:
        """
        Add a warning message.

        Args:
            message: Warning message to log
        """
        self.warnings.append(message)
        print(f"⚠️ WARNING [DataFusion] {message}")

    def to_state_update(self) -> Dict[str, Any]:
        """
        Convert the processed data back to AgentState update format.

        Returns:
            Dict containing keys for updating AgentState:
                - final_dataframe: List of records (dict format)
                - final_result_text: Debug logs summary
                - budget_note: Budget explanation (if any)
        """
        if self.df_final is None or self.df_final.empty:
            return {
                "final_dataframe": None,
                "final_result_text": "查無數據 (Processing failed or no data)"
            }

        # Convert DataFrame to list of dicts (records format)
        final_dataframe = self.df_final.to_dict('records')

        # Build result text from debug logs
        log_summary = " | ".join(self.debug_logs) if self.debug_logs else "No debug logs"
        result_text = f"Rows: {len(self.df_final)} | {log_summary}"

        # Extract budget note from metadata
        budget_note = self.metadata.get('budget_note', '')

        return {
            "final_dataframe": final_dataframe,
            "final_result_text": result_text,
            "budget_note": budget_note
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        mysql_rows = len(self.df_mysql) if self.df_mysql is not None else 0
        ch_rows = len(self.df_clickhouse) if self.df_clickhouse is not None else 0
        merged_rows = len(self.df_merged) if self.df_merged is not None else 0
        final_rows = len(self.df_final) if self.df_final is not None else 0

        return (
            f"<ProcessingContext "
            f"mysql={mysql_rows} rows, "
            f"ch={ch_rows} rows, "
            f"merged={merged_rows} rows, "
            f"final={final_rows} rows>"
        )
