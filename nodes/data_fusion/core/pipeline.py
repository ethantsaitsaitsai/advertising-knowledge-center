"""
DataFusion Pipeline - Main Orchestrator

The DataFusionPipeline coordinates all processing stages for data fusion.
It is responsible for assembling and executing the processor chain.
"""

from typing import Dict, Any, List, Optional
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

# Import LLM planner (Phase 3)
from nodes.data_fusion.planner import FusionPlanner, get_global_cache
from langchain_core.language_models import BaseChatModel


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
        planner (Optional[FusionPlanner]): LLM-based strategy planner (Phase 3)
        enable_llm_planner (bool): Whether to use LLM for strategic planning
    """

    def __init__(
        self,
        config: ConfigRegistry,
        llm: Optional[BaseChatModel] = None,
        enable_llm_planner: bool = False,
    ):
        """
        Initialize the DataFusion pipeline.

        Args:
            config: Configuration registry for accessing settings
            llm: Optional language model for LLM-based planning (Phase 3)
            enable_llm_planner: Whether to enable LLM strategic planning (Phase 3)
        """
        self.config = config
        self.processors: List[BaseProcessor] = []
        self.enable_llm_planner = enable_llm_planner

        # Initialize LLM planner (Phase 3)
        if enable_llm_planner and llm is not None:
            cache = get_global_cache()
            self.planner = FusionPlanner(llm=llm, cache=cache, enable_llm=True)
            print("DEBUG [Pipeline] LLM Planner enabled with caching")
        else:
            # Use rule-based planning (fallback)
            self.planner = FusionPlanner(llm=None, cache=None, enable_llm=False)
            print("DEBUG [Pipeline] Using rule-based planning (LLM disabled)")

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

        # Phase 3: LLM Strategic Planning (after data retrieval)
        # Note: Planning happens after IntentExtraction to get user's original dims/metrics
        # For now, we just record the strategy decision without using it
        # Phase 4 will make processors actually use the strategy

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

        In Phase 3, after IntentExtraction, we call the FusionPlanner to decide
        the optimal processing strategy.

        Args:
            context: The processing context

        Returns:
            ProcessingContext: The final processed context
        """
        for i, processor in enumerate(self.processors):
            # Phase 3: Call FusionPlanner after IntentExtraction
            # This ensures we have user_original_dims and user_original_metrics
            if processor.name == "IntentExtractionProcessor":
                if processor.should_execute(context):
                    context.add_debug_log(f"Executing: {processor.name}")
                    context = processor.process(context)
                else:
                    context.add_debug_log(f"Skipping: {processor.name}")

                # Now call FusionPlanner
                try:
                    strategy = self.planner.plan_strategy(context.state, context)
                    context.metadata['fusion_strategy'] = strategy
                    context.add_debug_log(f"FusionPlanner Strategy: {strategy.reasoning}")
                    print(f"DEBUG [Pipeline] Strategy Decision:\n{strategy}")
                except Exception as e:
                    context.add_debug_log(f"⚠️ FusionPlanner failed: {e}, using defaults")
                    print(f"⚠️ WARNING [Pipeline] FusionPlanner failed: {e}")

                continue  # Already executed, skip the normal flow

            # Normal processor execution
            if processor.should_execute(context):
                context.add_debug_log(f"Executing: {processor.name}")
                context = processor.process(context)
            else:
                context.add_debug_log(f"Skipping: {processor.name}")

        return context

    def __repr__(self) -> str:
        return f"<DataFusionPipeline processors={len(self.processors)}>"
