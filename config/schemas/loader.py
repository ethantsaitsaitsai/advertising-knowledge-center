"""
YAML configuration loader utility.
Loads YAML files and converts them to Pydantic models.
"""
from pathlib import Path
from typing import TypeVar, Type
import yaml
from pydantic import BaseModel

from config.schemas.metrics import MetricsConfiguration
from config.schemas.query_levels import QueryLevelConfiguration
from config.schemas.column_mappings import ColumnMappingConfiguration

T = TypeVar('T', bound=BaseModel)

# Configuration directory path
CONFIG_DIR = Path(__file__).parent.parent
YAML_DIR = CONFIG_DIR / "yaml"


def load_yaml(filename: str) -> dict:
    """
    Load a YAML file from the yaml directory.

    Args:
        filename: Name of the YAML file to load

    Returns:
        Parsed YAML content as dict

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    filepath = YAML_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Configuration file not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_config(filename: str, model_class: Type[T]) -> T:
    """
    Load a YAML file and parse it into a Pydantic model.

    Args:
        filename: Name of the YAML file
        model_class: Pydantic model class to instantiate

    Returns:
        Validated Pydantic model instance
    """
    data = load_yaml(filename)
    return model_class(**data)


def load_metrics_config() -> MetricsConfiguration:
    """Load metrics and dimensions configuration."""
    return load_config("metrics.yaml", MetricsConfiguration)


def load_query_levels_config() -> QueryLevelConfiguration:
    """Load query levels configuration."""
    return load_config("query_levels.yaml", QueryLevelConfiguration)


def load_column_mappings_config() -> ColumnMappingConfiguration:
    """Load column mappings configuration."""
    return load_config("column_mappings.yaml", ColumnMappingConfiguration)
