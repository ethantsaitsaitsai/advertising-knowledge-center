"""
Base Processor for DataFusion Pipeline

All processing stages inherit from BaseProcessor and implement the process() method.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodes.data_fusion.core.context import ProcessingContext


class BaseProcessor(ABC):
    """
    Abstract base class for all DataFusion processors.

    Each processor represents a single processing stage in the data fusion pipeline.
    Processors are executed in sequence, with each processor receiving and returning
    a ProcessingContext object.

    Attributes:
        name (str): Human-readable name of this processor
    """

    def __init__(self, name: str = None):
        """
        Initialize the processor.

        Args:
            name: Optional custom name for this processor.
                  If not provided, uses the class name.
        """
        self.name = name or self.__class__.__name__

    @abstractmethod
    def process(self, context: 'ProcessingContext') -> 'ProcessingContext':
        """
        Execute this processing stage.

        This is the main method that subclasses must implement. It receives
        a ProcessingContext, performs its specific data transformation, and
        returns the updated context.

        Args:
            context: The current processing context containing data and metadata

        Returns:
            ProcessingContext: The updated context after processing

        Raises:
            NotImplementedError: If subclass doesn't implement this method
        """
        raise NotImplementedError(f"{self.name} must implement process() method")

    def should_execute(self, context: 'ProcessingContext') -> bool:
        """
        Determine if this processor should be executed.

        Override this method to implement conditional execution logic.
        For example, PreAggregationProcessor only runs if segment columns exist.

        Args:
            context: The current processing context

        Returns:
            bool: True if this processor should run, False to skip
        """
        return True

    def __repr__(self) -> str:
        return f"<{self.name}>"
