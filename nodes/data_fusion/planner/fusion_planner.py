"""
FusionPlanner

LLM-based strategic planner for DataFusion processing.
"""

import json
import re
from typing import Optional
from langchain_core.language_models import BaseChatModel

from nodes.data_fusion.planner.fusion_strategy import FusionStrategy, create_default_strategy
from prompts.fusion_planner_prompt import build_fusion_planner_prompt
from schemas.state import AgentState


class FusionPlanner:
    """
    LLM-based planner for data fusion strategy.

    This class uses an LLM to intelligently decide the optimal processing
    strategy based on query characteristics. It can also fall back to
    rule-based decisions if LLM is unavailable or fails.

    Attributes:
        llm: Language model for strategic planning
        cache: Optional strategy cache for performance optimization
        enable_llm: Whether to use LLM (can be disabled for testing)
    """

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        cache: Optional['StrategyCache'] = None,
        enable_llm: bool = True,
    ):
        """
        Initialize the FusionPlanner.

        Args:
            llm: Language model instance (required if enable_llm=True)
            cache: Optional strategy cache
            enable_llm: Whether to use LLM decisions (default: True)
        """
        self.llm = llm
        self.cache = cache
        self.enable_llm = enable_llm and llm is not None

    def plan_strategy(self, state: AgentState, context: 'ProcessingContext') -> FusionStrategy:
        """
        Plan the optimal fusion strategy for the current query.

        Args:
            state: LangGraph AgentState with query information
            context: Processing context with DataFrames

        Returns:
            FusionStrategy with processing decisions
        """
        # 1. Build cache key
        cache_key = self._build_cache_key(state)

        # 2. Check cache
        if self.cache:
            cached_strategy = self.cache.get(cache_key)
            if cached_strategy:
                print(f"DEBUG [FusionPlanner] Cache HIT: {cache_key}")
                return cached_strategy

        # 3. Get strategy (LLM or rule-based)
        if self.enable_llm:
            try:
                strategy = self._plan_with_llm(state, context)
                print(f"DEBUG [FusionPlanner] LLM Decision: {strategy.reasoning}")
            except Exception as e:
                print(f"⚠️ WARNING [FusionPlanner] LLM failed ({e}), using fallback rules")
                strategy = self._plan_with_rules(state, context)
        else:
            strategy = self._plan_with_rules(state, context)

        # 4. Cache the result
        if self.cache:
            self.cache.set(cache_key, strategy, ttl=3600)  # 1 hour TTL

        return strategy

    def _build_cache_key(self, state: AgentState) -> str:
        """
        Build a cache key from query characteristics.

        Args:
            state: AgentState with query information

        Returns:
            Cache key string
        """
        query_level = state.get('query_level', 'strategy')

        # Extract dimensions and metrics
        user_intent = state.get('user_intent')
        if user_intent and user_intent.analysis_needs:
            analysis_needs = user_intent.analysis_needs
            if hasattr(analysis_needs, 'model_dump'):
                needs_dict = analysis_needs.model_dump()
            elif hasattr(analysis_needs, 'dict'):
                needs_dict = analysis_needs.dict()
            else:
                needs_dict = analysis_needs
        else:
            needs_dict = state.get('analysis_needs', {})

        dims = needs_dict.get('dimensions', [])
        metrics = needs_dict.get('metrics', [])

        # Sort for consistent keys
        dims_str = ','.join(sorted(dims)) if dims else 'none'
        metrics_str = ','.join(sorted(metrics)) if metrics else 'none'

        return f"{query_level}:{dims_str}:{metrics_str}"

    def _plan_with_llm(self, state: AgentState, context: 'ProcessingContext') -> FusionStrategy:
        """
        Use LLM to plan strategy.

        Args:
            state: AgentState with query information
            context: Processing context

        Returns:
            FusionStrategy from LLM decision
        """
        # Extract query characteristics
        query_level = state.get('query_level', 'strategy')

        user_intent = state.get('user_intent')
        if user_intent and user_intent.analysis_needs:
            analysis_needs = user_intent.analysis_needs
            if hasattr(analysis_needs, 'model_dump'):
                needs_dict = analysis_needs.model_dump()
            elif hasattr(analysis_needs, 'dict'):
                needs_dict = analysis_needs.dict()
            else:
                needs_dict = analysis_needs
        else:
            needs_dict = state.get('analysis_needs', {})

        user_dimensions = needs_dict.get('dimensions', [])
        user_metrics = needs_dict.get('metrics', [])

        mysql_columns = list(context.df_mysql.columns) if context.df_mysql is not None else []
        ch_columns = list(context.df_clickhouse.columns) if context.df_clickhouse is not None else []

        # Build prompt
        prompt = build_fusion_planner_prompt(
            query_level=query_level,
            user_dimensions=user_dimensions,
            user_metrics=user_metrics,
            mysql_columns=mysql_columns,
            clickhouse_columns=ch_columns,
        )

        # Call LLM
        response = self.llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)

        # Parse JSON response
        strategy_dict = self._parse_llm_response(response_text)

        # Create FusionStrategy
        return FusionStrategy.from_dict(strategy_dict)

    def _parse_llm_response(self, response_text: str) -> dict:
        """
        Parse LLM response to extract JSON strategy.

        Args:
            response_text: LLM response text (may contain markdown or extra text)

        Returns:
            Parsed strategy dictionary

        Raises:
            ValueError: If JSON parsing fails
        """
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            else:
                raise ValueError(f"No JSON found in LLM response: {response_text[:200]}")

        # Parse JSON
        try:
            strategy_dict = json.loads(json_text)
            return strategy_dict
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in LLM response: {e}\nText: {json_text[:200]}")

    def _plan_with_rules(self, state: AgentState, context: 'ProcessingContext') -> FusionStrategy:
        """
        Use rule-based logic to plan strategy (fallback when LLM unavailable).

        Args:
            state: AgentState with query information
            context: Processing context

        Returns:
            FusionStrategy from rule-based decisions
        """
        query_level = state.get('query_level', 'strategy')

        # Extract user intent
        user_intent = state.get('user_intent')
        if user_intent and user_intent.analysis_needs:
            analysis_needs = user_intent.analysis_needs
            if hasattr(analysis_needs, 'model_dump'):
                needs_dict = analysis_needs.model_dump()
            elif hasattr(analysis_needs, 'dict'):
                needs_dict = analysis_needs.dict()
            else:
                needs_dict = analysis_needs
        else:
            needs_dict = state.get('analysis_needs', {})

        user_dimensions = needs_dict.get('dimensions', [])
        user_metrics = needs_dict.get('metrics', [])

        # Detect data characteristics
        mysql_columns = list(context.df_mysql.columns) if context.df_mysql is not None else []
        has_segment = any('segment' in col.lower() for col in mysql_columns)
        has_ad_format = any('ad_format' in col.lower() for col in mysql_columns)

        # Rule 1: Pre-Aggregation
        use_pre_agg = (
            query_level == 'audience' and
            has_segment and
            any('segment' in dim.lower() for dim in user_dimensions)
        )

        # Rule 2: Merge Keys
        if has_ad_format and (
            any('ad_format' in dim.lower() for dim in user_dimensions) or
            any(m.lower() in ['ctr', 'vtr', 'er', 'impression', 'click'] for m in user_metrics)
        ):
            merge_keys = ['cmpid', 'ad_format_type_id']
        else:
            merge_keys = ['cmpid']

        # Rule 3: Aggregation Mode
        aggregation_mode = "total" if not user_dimensions else "dimension"

        # Rule 4: Ad Format Filtering
        if 'ad_format' in [d.lower() for d in user_dimensions]:
            has_performance = any(
                m.lower() in ['ctr', 'vtr', 'er', 'impression', 'click']
                for m in user_metrics
            )
            filter_ad_format = "strict" if has_performance else "loose"
        else:
            filter_ad_format = "none"

        # Rule 5: Sorting Strategy
        calc_type = needs_dict.get('calculation_type', 'Total')
        if calc_type == 'Ranking':
            sorting_strategy = "ranking"
        elif calc_type == 'Trend':
            sorting_strategy = "trend"
        else:
            sorting_strategy = "none"

        # Rule 6: Hide Zero Metrics
        hide_zero_metrics = True

        return FusionStrategy(
            use_pre_aggregation=use_pre_agg,
            merge_keys=merge_keys,
            aggregation_mode=aggregation_mode,
            filter_ad_format=filter_ad_format,
            sorting_strategy=sorting_strategy,
            hide_zero_metrics=hide_zero_metrics,
            reasoning="Rule-based strategy (LLM unavailable or disabled)",
        )
