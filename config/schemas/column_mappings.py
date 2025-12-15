"""
Pydantic models for column mapping configuration.
Defines column aliases, exclusions, and display preferences.
"""
from typing import List, Optional, Dict, Union
from pydantic import BaseModel, Field


class ColumnAlias(BaseModel):
    """Single column alias configuration."""
    target: str = Field(..., description="Primary target column name")
    alternatives: List[str] = Field(
        default_factory=list, description="Alternative column names in priority order"
    )


class MetricColumnDiscovery(BaseModel):
    """Configuration for discovering metric columns."""
    keywords: List[str] = Field(default_factory=list)
    prefer_first: bool = Field(True, description="Return first match")


class MetricAggregationRules(BaseModel):
    """Rules for metric aggregation."""
    sum_keywords: List[str] = Field(default_factory=list)
    default_numeric: str = Field("sum")
    default_text: str = Field("first")
    budget_special: str = Field("max")


class ExcludeFromGrouping(BaseModel):
    """Columns to exclude from grouping operations."""
    keywords: List[str] = Field(default_factory=list)
    strict_keywords: List[str] = Field(default_factory=list)


class ColumnMappingConfiguration(BaseModel):
    """Complete column mapping configuration."""
    version: str = Field("1.0")
    intent_to_column: Dict[str, ColumnAlias] = Field(default_factory=dict)
    metric_column_discovery: Dict[str, MetricColumnDiscovery] = Field(default_factory=dict)
    exclude_from_grouping: ExcludeFromGrouping = Field(
        default_factory=ExcludeFromGrouping
    )
    hidden_columns: List[str] = Field(default_factory=list)
    segment_column_candidates: List[str] = Field(default_factory=list)
    display_order: List[str] = Field(default_factory=list)
    metric_aggregation_rules: MetricAggregationRules = Field(
        default_factory=MetricAggregationRules
    )

    def get_intent_alias(self, intent_key: str) -> Optional[ColumnAlias]:
        """Get column alias configuration for an intent."""
        return self.intent_to_column.get(intent_key)

    def build_intent_to_alias_map(self) -> Dict[str, Union[str, List[str]]]:
        """
        Build the legacy intent_to_alias dict format for backward compatibility.

        Returns:
            Dict where value is either a string (single target) or list
            (target + alternatives)
        """
        result = {}
        for key, alias_config in self.intent_to_column.items():
            if alias_config.alternatives:
                # Return list with target first, then alternatives
                result[key] = [alias_config.target] + alias_config.alternatives
            else:
                result[key] = alias_config.target
        return result

    def find_column(self, keywords: List[str], columns: List[str]) -> Optional[str]:
        """
        Find a column matching any of the keywords (case-insensitive).

        Args:
            keywords: List of keywords to search for
            columns: List of available column names

        Returns:
            First matching column name or None
        """
        col_lower_map = {c.lower(): c for c in columns}
        for kw in keywords:
            if kw.lower() in col_lower_map:
                return col_lower_map[kw.lower()]
        return None

    def get_metric_keywords(self, metric_key: str) -> List[str]:
        """
        Get keywords for finding a metric column.

        Args:
            metric_key: The metric identifier (e.g., 'impressions', 'clicks')

        Returns:
            List of keywords to search for
        """
        discovery = self.metric_column_discovery.get(metric_key)
        return discovery.keywords if discovery else []
