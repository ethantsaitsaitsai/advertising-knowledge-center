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

        # Phase 1: No processors yet, using legacy logic
        # Phase 2+: Will initialize processors here
        # self._initialize_processors()

    def _initialize_processors(self) -> None:
        """
        Initialize the processor chain.

        In Phase 2+, this method will create instances of all processors
        in the correct order. For now, this is a placeholder.
        """
        # TODO Phase 2: Initialize processors
        # Example:
        # self.processors = [
        #     DataRetrievalProcessor(),
        #     StandardizationProcessor(),
        #     IntentExtractionProcessor(),
        #     ...
        # ]
        pass

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

        # Phase 1: Use legacy implementation directly
        # This ensures backward compatibility while we build the new architecture
        result = self._execute_legacy(state)

        # Phase 2+: Use modular processors
        # context = self._execute_processors(context)
        # result = context.to_state_update()

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
