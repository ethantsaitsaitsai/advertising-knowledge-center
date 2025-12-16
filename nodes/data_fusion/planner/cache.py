"""
StrategyCache

Simple in-memory cache for FusionStrategy with TTL and hit rate tracking.
"""

import time
from typing import Dict, Optional, Tuple
from nodes.data_fusion.planner.fusion_strategy import FusionStrategy


class StrategyCache:
    """
    In-memory cache for FusionStrategy with TTL expiration.

    This cache stores LLM-decided strategies to avoid expensive LLM calls
    for repeated queries. Target: 80% hit rate, <50ms cache hit latency.

    Attributes:
        _cache: Dictionary mapping cache keys to (strategy, expire_time) tuples
        _hits: Number of cache hits
        _misses: Number of cache misses
    """

    def __init__(self):
        """Initialize empty cache."""
        self._cache: Dict[str, Tuple[FusionStrategy, float]] = {}
        self._hits: int = 0
        self._misses: int = 0

    def get(self, key: str) -> Optional[FusionStrategy]:
        """
        Get a strategy from cache.

        Args:
            key: Cache key

        Returns:
            FusionStrategy if found and not expired, None otherwise
        """
        if key not in self._cache:
            self._misses += 1
            return None

        strategy, expire_time = self._cache[key]

        # Check if expired
        if time.time() > expire_time:
            # Expired, remove from cache
            del self._cache[key]
            self._misses += 1
            return None

        # Cache hit
        self._hits += 1
        return strategy

    def set(self, key: str, strategy: FusionStrategy, ttl: int = 3600) -> None:
        """
        Store a strategy in cache with TTL.

        Args:
            key: Cache key
            strategy: FusionStrategy to cache
            ttl: Time to live in seconds (default: 3600 = 1 hour)
        """
        expire_time = time.time() + ttl
        self._cache[key] = (strategy, expire_time)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache.

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = [
            key for key, (_, expire_time) in self._cache.items()
            if current_time > expire_time
        ]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)

    def get_stats(self) -> Dict[str, any]:
        """
        Get cache statistics.

        Returns:
            Dict with hit rate, size, hits, misses
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "hit_rate": round(hit_rate, 2),
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total_requests,
            "cache_size": len(self._cache),
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        stats = self.get_stats()
        return (
            f"<StrategyCache "
            f"hit_rate={stats['hit_rate']}% "
            f"size={stats['cache_size']} "
            f"hits={stats['hits']} "
            f"misses={stats['misses']}>"
        )


# Global singleton cache instance (optional, can be disabled)
_global_cache: Optional[StrategyCache] = None


def get_global_cache() -> StrategyCache:
    """
    Get or create the global cache instance.

    Returns:
        Global StrategyCache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = StrategyCache()
    return _global_cache


def reset_global_cache() -> None:
    """Reset the global cache (useful for testing)."""
    global _global_cache
    _global_cache = None
