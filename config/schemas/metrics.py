"""
Pydantic models for metrics and dimensions configuration.
Provides type-safe access to YAML-defined configurations.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class DimensionConfig(BaseModel):
    """Configuration for a single dimension."""
    display_name: str = Field(..., description="Canonical display name")
    aliases: List[str] = Field(default_factory=list, description="Alternative names")
    mysql_column: Optional[str] = Field(None, description="MySQL column reference")
    clickhouse_column: Optional[str] = Field(None, description="ClickHouse column reference")
    description: Optional[str] = Field(None, description="Dimension description")

    def matches(self, term: str) -> bool:
        """Check if a term matches this dimension (case-insensitive)."""
        term_lower = term.lower()
        return (
            term_lower == self.display_name.lower() or
            term_lower in [a.lower() for a in self.aliases]
        )


class MetricConfig(BaseModel):
    """Configuration for a single metric."""
    display_name: str = Field(..., description="Canonical display name")
    aliases: List[str] = Field(default_factory=list, description="Alternative names")
    keywords: List[str] = Field(default_factory=list, description="Column discovery keywords")
    formula: Optional[str] = Field(None, description="Calculation formula")
    aggregation: str = Field("sum", description="Aggregation type: sum, calculate, etc.")
    description: Optional[str] = Field(None, description="Metric description")

    def matches(self, term: str) -> bool:
        """Check if a term matches this metric (case-insensitive)."""
        term_lower = term.lower()
        return (
            term_lower == self.display_name.lower() or
            term_lower in [a.lower() for a in self.aliases] or
            any(kw in term_lower for kw in self.keywords)
        )


class MetricsDefaultsConfig(BaseModel):
    """Default metrics configuration."""
    performance_metrics: List[str] = Field(default_factory=list)
    generic_keywords: List[str] = Field(default_factory=list)


class MetricsConfiguration(BaseModel):
    """Complete metrics and dimensions configuration."""
    version: str = Field("1.0")
    dimensions: Dict[str, DimensionConfig] = Field(default_factory=dict)
    metrics: Dict[str, MetricConfig] = Field(default_factory=dict)
    defaults: MetricsDefaultsConfig = Field(default_factory=MetricsDefaultsConfig)

    def get_dimension(self, key: str) -> Optional[DimensionConfig]:
        """Get dimension by key or alias."""
        key_lower = key.lower()
        if key_lower in self.dimensions:
            return self.dimensions[key_lower]
        for dim in self.dimensions.values():
            if dim.matches(key):
                return dim
        return None

    def get_metric(self, key: str) -> Optional[MetricConfig]:
        """Get metric by key or alias."""
        key_lower = key.lower()
        if key_lower in self.metrics:
            return self.metrics[key_lower]
        for metric in self.metrics.values():
            if metric.matches(key):
                return metric
        return None

    def normalize_dimension(self, term: str) -> Optional[str]:
        """Convert a dimension alias to its canonical display name."""
        dim = self.get_dimension(term)
        return dim.display_name if dim else None

    def normalize_metric(self, term: str) -> Optional[str]:
        """Convert a metric alias to its canonical display name."""
        metric = self.get_metric(term)
        return metric.display_name if metric else None

    def get_valid_dimensions_map(self) -> Dict[str, str]:
        """
        Return alias -> display_name map for dimensions.
        For backward compatibility with existing code.
        """
        result = {}
        for dim in self.dimensions.values():
            for alias in dim.aliases:
                result[alias.lower()] = dim.display_name
        return result

    def get_valid_metrics_list(self) -> List[str]:
        """
        Return list of valid metric keys.
        For backward compatibility with existing code.
        """
        return list(self.metrics.keys())
