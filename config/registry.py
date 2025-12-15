"""
Configuration Registry - Singleton pattern for global config access.
Lazy-loads configurations on first access and caches them.
"""
from typing import Optional, Dict, List, Union

from config.schemas.metrics import MetricsConfiguration
from config.schemas.query_levels import QueryLevelConfiguration
from config.schemas.column_mappings import ColumnMappingConfiguration
from config.schemas.loader import (
    load_metrics_config,
    load_query_levels_config,
    load_column_mappings_config
)


class ConfigRegistry:
    """
    Singleton registry for configuration access.
    Caches loaded configurations for performance.

    Usage:
        from config.registry import config

        # Access configurations
        dims = config.get_valid_dimensions()
        metrics = config.get_valid_metrics()

        # Or access the raw config objects
        dim_config = config.metrics.get_dimension("agency")
    """
    _instance: Optional['ConfigRegistry'] = None
    _metrics: Optional[MetricsConfiguration] = None
    _query_levels: Optional[QueryLevelConfiguration] = None
    _column_mappings: Optional[ColumnMappingConfiguration] = None

    def __new__(cls) -> 'ConfigRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def metrics(self) -> MetricsConfiguration:
        """Get metrics configuration (lazy-loaded)."""
        if self._metrics is None:
            self._metrics = load_metrics_config()
        return self._metrics

    @property
    def query_levels(self) -> QueryLevelConfiguration:
        """Get query levels configuration (lazy-loaded)."""
        if self._query_levels is None:
            self._query_levels = load_query_levels_config()
        return self._query_levels

    @property
    def column_mappings(self) -> ColumnMappingConfiguration:
        """Get column mappings configuration (lazy-loaded)."""
        if self._column_mappings is None:
            self._column_mappings = load_column_mappings_config()
        return self._column_mappings

    def reload(self) -> None:
        """Force reload all configurations (useful for testing)."""
        self._metrics = None
        self._query_levels = None
        self._column_mappings = None

    # ============================================================
    # BACKWARD COMPATIBILITY METHODS
    # ============================================================
    # These methods provide the same interface as the original
    # hard-coded variables for easy migration.

    def get_valid_dimensions(self) -> Dict[str, str]:
        """
        Get VALID_DIMENSIONS map for backward compatibility.

        Returns:
            Dict mapping lowercase aliases to display names.
            Example: {"agency": "Agency", "廣告主": "Advertiser"}
        """
        return self.metrics.get_valid_dimensions_map()

    def get_valid_metrics(self) -> List[str]:
        """
        Get VALID_METRICS list for backward compatibility.

        Returns:
            List of valid metric keys.
            Example: ["budget_sum", "ctr", "vtr", "er", "impression", "click"]
        """
        return self.metrics.get_valid_metrics_list()

    def get_default_performance_metrics(self) -> List[str]:
        """
        Get default metrics for performance queries.

        Returns:
            List of default metric display names.
            Example: ["Impression", "Click", "CTR", "VTR", "ER"]
        """
        return self.metrics.defaults.performance_metrics

    def get_generic_keywords(self) -> List[str]:
        """
        Get generic performance keywords.

        Returns:
            List of keywords that trigger default performance metrics.
            Example: ["成效", "成效數據", "performance", "metrics"]
        """
        return self.metrics.defaults.generic_keywords

    def get_intent_to_alias_map(self) -> Dict[str, Union[str, List[str]]]:
        """
        Get intent_to_alias for data fusion backward compatibility.

        Returns:
            Dict where value is either a string (single target) or list
            (target + alternatives in priority order).
        """
        return self.column_mappings.build_intent_to_alias_map()

    def get_exclude_keywords(self) -> List[str]:
        """
        Get exclude_keywords for grouping operations.

        Returns:
            List of column name keywords to exclude from grouping.
        """
        return self.column_mappings.exclude_from_grouping.keywords

    def get_strict_exclude_keywords(self) -> List[str]:
        """
        Get strict_exclude_keywords for filtering operations.

        Returns:
            List of column name keywords for strict exclusion.
        """
        return self.column_mappings.exclude_from_grouping.strict_keywords

    def get_hidden_columns(self) -> List[str]:
        """
        Get cols_to_hide for final display.

        Returns:
            List of technical ID columns to hide.
        """
        return self.column_mappings.hidden_columns

    def get_display_order(self) -> List[str]:
        """
        Get preferred_order for column display.

        Returns:
            List of column names in preferred display order.
        """
        return self.column_mappings.display_order

    def get_segment_column_candidates(self) -> List[str]:
        """
        Get segment column candidates for special aggregation.

        Returns:
            List of possible segment column names.
        """
        return self.column_mappings.segment_column_candidates

    def get_metric_keywords(self, metric_key: str) -> List[str]:
        """
        Get keywords for finding a metric column.

        Args:
            metric_key: The metric identifier (e.g., 'impressions', 'clicks')

        Returns:
            List of keywords to search for.
        """
        return self.column_mappings.get_metric_keywords(metric_key)

    def get_fallback_tables(self, query_level: str) -> List[str]:
        """
        Get fallback tables for a query level.

        Args:
            query_level: The query level string

        Returns:
            List of table names to use as fallback.
        """
        return self.query_levels.get_fallback_tables(query_level)


# Global singleton instance
config = ConfigRegistry()
