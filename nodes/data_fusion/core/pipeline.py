"""
DataFusion Pipeline - Main Orchestrator

The DataFusionPipeline coordinates all processing stages for data fusion.
It is responsible for assembling and executing the processor chain.
"""

from typing import Dict, Any, List
from schemas.state import AgentState
from config.registry import ConfigRegistry
from nodes.data_fusion.core.context import ProcessingContext
from nodes.data_fusion.core.processor import BaseProcessor

# Import all processors
from nodes.data_fusion.processors import (
    DataRetrievalProcessor,
    StandardizationProcessor,
    IntentExtractionProcessor,
    PreAggregationProcessor,
    DataMergeProcessor,
    AggregationProcessor,
    KPICalculator,
    ColumnFilterProcessor,
    SortingProcessor,
    FormattingProcessor,
)
from nodes.data_fusion.validators import BudgetValidator


class DataFusionPipeline:
    """
    Main orchestrator for the DataFusion pipeline.

    This class coordinates the execution of all data processing stages,
    from raw data retrieval to final formatted output.

    In Phase 1, this uses the legacy data_fusion_node logic directly.
    In Phase 2+, this will use modular processors.

    Attributes:
        config (ConfigRegistry): Configuration registry
        processors (List[BaseProcessor]): List of processors to execute
    """

    def __init__(self, config: ConfigRegistry):
        """
        Initialize the DataFusion pipeline.

        Args:
            config: Configuration registry for accessing settings
        """
        self.config = config
        self.processors: List[BaseProcessor] = []

        # Initialize the processor chain
        self._initialize_processors()

    def _initialize_processors(self) -> None:
        """
        Initialize the processor chain.

        Processors are executed in this order:
        1. Data Retrieval - Extract data from state
        2. Standardization - Normalize column names and types
        3. Pre-Aggregation - Segment deduplication (conditional)
        4. Intent Extraction - Extract user's original request
        5. Data Merge - Merge MySQL + ClickHouse
        6. Aggregation - Re-aggregate by user dimensions
        7. Budget Validator - Validate budget consistency
        8. KPI Calculator - Calculate derived metrics (CTR/VTR/ER)
        9. Column Filter - Remove unwanted enriched columns
        10. Sorting - Sort and limit rows
        11. Formatting - Final cleanup and display formatting
        """
        self.processors = [
            DataRetrievalProcessor(),
            StandardizationProcessor(),
            PreAggregationProcessor(self.config),
            IntentExtractionProcessor(),
            DataMergeProcessor(),
            AggregationProcessor(self.config),
            BudgetValidator(),
            KPICalculator(self.config),
            ColumnFilterProcessor(self.config),
            SortingProcessor(),
            FormattingProcessor(self.config),
        ]

    def execute(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute the data fusion pipeline.

        Args:
            state: The LangGraph AgentState containing raw data

        Returns:
            Dict with keys:
                - final_dataframe: Processed data as list of dicts
                - final_result_text: Debug logs summary
                - budget_note: Budget explanation (if any)
        """
        # Create processing context
        context = ProcessingContext(state)

        # Execute all processors in sequence
        context = self._execute_processors(context)

        # Convert context to state update format
        result = context.to_state_update()

        return result

    def _execute_legacy(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute using the legacy data_fusion_node implementation.

        This is a temporary method for Phase 1 to ensure backward compatibility.
        Will be removed in Phase 2 once all processors are extracted.

        Args:
            state: The LangGraph AgentState

        Returns:
            Dict with processed data
        """
        # Import the legacy implementation
        from nodes.data_fusion_legacy import data_fusion_node as legacy_data_fusion_node

        return legacy_data_fusion_node(state)

    def _execute_processors(self, context: ProcessingContext) -> ProcessingContext:
        """
        Execute all processors in sequence.

        Each processor receives the context, processes it, and returns the updated context.
        Processors can be skipped based on their should_execute() method.

        Args:
            context: The processing context

        Returns:
            ProcessingContext: The final processed context
        """
        for processor in self.processors:
            if processor.should_execute(context):
                context.add_debug_log(f"Executing: {processor.name}")
                context = processor.process(context)
            else:
                context.add_debug_log(f"Skipping: {processor.name}")

        return context

    def __repr__(self) -> str:
        return f"<DataFusionPipeline processors={len(self.processors)}>"
