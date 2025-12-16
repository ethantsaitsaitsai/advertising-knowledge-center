"""
IntentExtractionProcessor

Extracts the user's ORIGINAL intent (dimensions/metrics) before enrichment
by PerformanceGenerator or other agents.
"""

from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext


class IntentExtractionProcessor(BaseProcessor):
    """
    Extract user's original analysis intent.

    This processor retrieves the user's ORIGINAL requested dimensions and metrics
    from the state, before they are enriched by PerformanceGenerator (which adds
    cmpid, campaign_name, etc.).

    This is critical for downstream processors like ColumnFilterProcessor to
    distinguish between user-requested fields vs enriched fields.

    Input:
        - context.state: AgentState with user_intent or analysis_needs

    Output:
        - context.metadata['user_original_dims']: List of original dimensions
        - context.metadata['user_original_metrics']: List of original metrics

    Example:
        User Query: "2025年悠遊卡的進單金額"
        - Original Dimensions: []
        - Original Metrics: ['Budget_Sum']

        After PerformanceGenerator enrichment:
        - Enriched Dimensions: ['cmpid', 'campaign_name']
        - Enriched Metrics: ['Budget_Sum', 'CTR', 'VTR', 'ER']
    """

    def __init__(self):
        super().__init__(name="IntentExtractionProcessor")

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Extract user's original intent from state.

        Args:
            context: Processing context

        Returns:
            Updated context with user_original_dims and user_original_metrics
        """
        state = context.state

        # 1. Get user's ORIGINAL intent (not enriched)
        user_intent = state.get('user_intent')
        if user_intent and user_intent.analysis_needs:
            raw_analysis_needs = user_intent.analysis_needs
        else:
            raw_analysis_needs = state.get('analysis_needs')

        # 2. Convert to dict format (handles Pydantic models or plain dicts)
        if hasattr(raw_analysis_needs, 'model_dump'):
            user_original_analysis_needs = raw_analysis_needs.model_dump()
        elif hasattr(raw_analysis_needs, 'dict'):
            user_original_analysis_needs = raw_analysis_needs.dict()
        elif isinstance(raw_analysis_needs, dict):
            user_original_analysis_needs = raw_analysis_needs
        else:
            user_original_analysis_needs = {}

        # 3. Extract dimensions and metrics
        user_original_dims = user_original_analysis_needs.get('dimensions', [])
        user_original_metrics = user_original_analysis_needs.get('metrics', [])

        # 4. Store in context metadata
        context.metadata['user_original_dims'] = user_original_dims
        context.metadata['user_original_metrics'] = user_original_metrics

        # 5. Add debug logs
        context.add_debug_log(f"User Original Dimensions: {user_original_dims}")
        context.add_debug_log(f"User Original Metrics: {user_original_metrics}")

        return context

    def should_execute(self, context: ProcessingContext) -> bool:
        """Always execute - intent extraction is mandatory."""
        return True
