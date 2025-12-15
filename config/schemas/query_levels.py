"""
Pydantic models for query level configuration.
Defines the mapping between query levels and database tables/strategies.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class QueryLevelConfig(BaseModel):
    """Configuration for a single query level."""
    display_name: str = Field(..., description="Display name")
    aliases: List[str] = Field(default_factory=list, description="Alternative names/keywords")
    description: str = Field("", description="Level description")
    root_table: Optional[str] = Field(None, description="Primary database table")
    required_tables: List[str] = Field(default_factory=list)
    optional_tables: List[str] = Field(default_factory=list)
    required_select: List[str] = Field(
        default_factory=list, description="Required SELECT clauses"
    )
    budget_formula: Optional[str] = Field(None, description="SQL formula for budget")
    budget_alias: Optional[str] = Field(None, description="Budget column alias")
    default_group_by: Optional[str] = Field(None, description="Default GROUP BY clause")
    supports_format_grouping: bool = Field(False)
    segment_aggregation: Optional[str] = Field(None, description="Segment aggregation SQL")


class QueryLevelConfiguration(BaseModel):
    """Complete query levels configuration."""
    version: str = Field("1.0")
    query_levels: Dict[str, QueryLevelConfig] = Field(default_factory=dict)
    priority_order: List[str] = Field(default_factory=list)
    valid_levels: List[str] = Field(default_factory=list)

    def get_level(self, key: str) -> Optional[QueryLevelConfig]:
        """Get query level by key."""
        return self.query_levels.get(key.lower())

    def get_root_table(self, level: str) -> Optional[str]:
        """Get root table for a query level."""
        config = self.get_level(level)
        return config.root_table if config else None

    def get_fallback_tables(self, level: str) -> List[str]:
        """
        Get fallback tables for schema_tool when AI selection fails.

        Args:
            level: The query level string

        Returns:
            List of table names to use as fallback
        """
        config = self.get_level(level)
        if not config:
            return ["one_campaigns"]  # Ultimate fallback

        if config.required_tables:
            return config.required_tables
        elif config.root_table:
            return [config.root_table]
        else:
            return ["one_campaigns"]

    def get_valid_levels_tuple(self) -> tuple:
        """Return tuple for Literal type annotation."""
        return tuple(self.valid_levels)
