"""
DataFusion Module

This module provides data fusion functionality to integrate MySQL (CampaignAgent)
and ClickHouse (PerformanceAgent) data.

The module has been refactored into a modular pipeline architecture:
- core/: Core infrastructure (Pipeline, Context, BaseProcessor)
- processors/: Individual processing stages
- validators/: Data validation processors
- planner/: LLM-based strategy planning (Phase 3+)
- utils/: Utility functions

Main entry point: data_fusion_node(state) - maintains backward compatibility
"""

from typing import Dict, Any
from schemas.state import AgentState
from nodes.data_fusion.core.pipeline import DataFusionPipeline

# Global pipeline instance (singleton pattern)
_pipeline = None


def data_fusion_node(state: AgentState) -> Dict[str, Any]:
    """
    Main entry point for DataFusion processing.

    This function maintains backward compatibility with the original interface
    used by ResponseSynthesizer and other components. Internally, it delegates
    to the new modular pipeline architecture.

    Args:
        state: AgentState containing:
            - sql_result: MySQL data (or campaign_data as fallback)
            - sql_result_columns: Column names for MySQL data
            - clickhouse_result: ClickHouse data (optional)
            - user_intent: Original user intent (for dimension/metric extraction)
            - query_level: Contract/Strategy/Execution/Audience
            - was_default_metrics: Whether metrics were auto-added

    Returns:
        Dict containing:
            - final_dataframe: Processed data as list of dicts
            - final_result_text: Debug logs and row count
            - budget_note: Budget explanation based on query_level

    Example:
        >>> result = data_fusion_node(state)
        >>> df = pd.DataFrame(result['final_dataframe'])
        >>> print(result['final_result_text'])
    """
    global _pipeline

    # Lazy initialization of pipeline (singleton)
    if _pipeline is None:
        from config.registry import config
        _pipeline = DataFusionPipeline(config)

    # Execute pipeline
    return _pipeline.execute(state)


# Re-export for convenience
__all__ = ['data_fusion_node']
