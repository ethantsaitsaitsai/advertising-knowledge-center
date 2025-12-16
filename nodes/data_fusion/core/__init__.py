"""
DataFusion Core Module

This module contains the core infrastructure for the DataFusion pipeline.
"""

from nodes.data_fusion.core.processor import BaseProcessor
from nodes.data_fusion.core.context import ProcessingContext
from nodes.data_fusion.core.pipeline import DataFusionPipeline

__all__ = ['BaseProcessor', 'ProcessingContext', 'DataFusionPipeline']
