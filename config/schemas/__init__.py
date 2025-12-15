"""
Configuration schema models for the Text-to-SQL system.
Provides type-safe access to YAML-defined configurations.
"""
from config.schemas.metrics import (
    DimensionConfig,
    MetricConfig,
    MetricsDefaultsConfig,
    MetricsConfiguration
)
from config.schemas.query_levels import (
    QueryLevelConfig,
    QueryLevelConfiguration
)
from config.schemas.column_mappings import (
    ColumnAlias,
    MetricColumnDiscovery,
    MetricAggregationRules,
    ColumnMappingConfiguration
)

__all__ = [
    # Metrics
    "DimensionConfig",
    "MetricConfig",
    "MetricsDefaultsConfig",
    "MetricsConfiguration",
    # Query Levels
    "QueryLevelConfig",
    "QueryLevelConfiguration",
    # Column Mappings
    "ColumnAlias",
    "MetricColumnDiscovery",
    "MetricAggregationRules",
    "ColumnMappingConfiguration",
]
