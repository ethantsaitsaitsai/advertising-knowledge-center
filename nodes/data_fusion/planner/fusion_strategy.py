"""
FusionStrategy

Data class representing the LLM-decided processing strategy.
"""

from dataclasses import dataclass
from typing import List, Literal


@dataclass
class FusionStrategy:
    """
    Strategy decisions for DataFusion processing.

    This class encapsulates all strategic decisions made by the FusionPlanner
    (LLM-based or rule-based) about how to process the data.

    Attributes:
        use_pre_aggregation: Whether to deduplicate segments before merge
        merge_keys: Keys to use for MySQL + ClickHouse merge
        aggregation_mode: How to aggregate data (total/dimension/none)
        filter_ad_format: Ad Format filtering strategy (strict/loose/none)
        sorting_strategy: How to sort results (ranking/trend/none)
        hide_zero_metrics: Whether to hide all-zero default metrics
        reasoning: Brief explanation of strategy choice (for debugging)
    """

    use_pre_aggregation: bool
    merge_keys: List[str]
    aggregation_mode: Literal["total", "dimension", "none"]
    filter_ad_format: Literal["strict", "loose", "none"]
    sorting_strategy: Literal["ranking", "trend", "none"]
    hide_zero_metrics: bool
    reasoning: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "use_pre_aggregation": self.use_pre_aggregation,
            "merge_keys": self.merge_keys,
            "aggregation_mode": self.aggregation_mode,
            "filter_ad_format": self.filter_ad_format,
            "sorting_strategy": self.sorting_strategy,
            "hide_zero_metrics": self.hide_zero_metrics,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'FusionStrategy':
        """Create from dictionary."""
        return cls(
            use_pre_aggregation=data["use_pre_aggregation"],
            merge_keys=data["merge_keys"],
            aggregation_mode=data["aggregation_mode"],
            filter_ad_format=data["filter_ad_format"],
            sorting_strategy=data["sorting_strategy"],
            hide_zero_metrics=data["hide_zero_metrics"],
            reasoning=data.get("reasoning", ""),
        )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<FusionStrategy "
            f"pre_agg={self.use_pre_aggregation} "
            f"merge={self.merge_keys} "
            f"agg={self.aggregation_mode} "
            f"filter_fmt={self.filter_ad_format} "
            f"sort={self.sorting_strategy}>"
        )


def create_default_strategy() -> FusionStrategy:
    """
    Create a default fallback strategy.

    This is used when LLM decision fails or is disabled.
    Conservative settings that work for most queries.
    """
    return FusionStrategy(
        use_pre_aggregation=False,
        merge_keys=["cmpid"],
        aggregation_mode="dimension",
        filter_ad_format="none",
        sorting_strategy="ranking",
        hide_zero_metrics=True,
        reasoning="Default fallback strategy",
    )
