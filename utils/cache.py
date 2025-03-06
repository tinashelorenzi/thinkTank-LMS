"""
Caching utilities
"""
import json
import time
import logging
import hashlib
from typing import Any, Dict, Optional, Callable, TypeVar, Union, List, Set, Tuple
from functools import wraps

# Redis client - only import if available
try:
    import redis
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from core.config import settings

# Configure logger
logger = logging.getLogger(__name__)

# Type variable for function return type
T = TypeVar('T')

# In-memory cache as a fallback
MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}


class Cache:
    """
    Simple cache wrapper supporting both Redis and in-memory fallback
    """
    
    def __init__(self, prefix: str = "lms"):
        """
        Initialize cache
        
        Args:
            prefix: Cache key prefix
        """
        self.prefix = prefix
        self.redis_client = None
        
        # Initialize Redis client if available
        if REDIS_AVAILABLE and settings.REDIS_URL:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
                logger.info("Redis cache initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis cache: {e}")
    
    def get_key(self, key: str) -> str:
        """
        Get prefixed cache key
        
        Args:
            key: Original key
            
        Returns:
            Prefixed key
        """
        return f"{self.prefix}:{key}"
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache
        
        Args:
            key: Cache key
            default: Default value if key not found
            
        Returns:
            Cached value or default
        """
        prefixed_key = self.get_key(key)
        
        # Try Redis first if available
        if self.redis_client:
            try:
                value = self.redis_client.get(prefixed_key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Redis get error for key {key}: {e}")
        
        # Fallback to memory cache
        if prefixed_key in MEMORY_CACHE:
            cache_item = MEMORY_CACHE[prefixed_key]
            if cache_item.get('expires_at', float('inf')) > time.time():
                return cache_item['value']
            else:
                # Expired
                del MEMORY_CACHE[prefixed_key]
        
        return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        prefixed_key = self.get_key(key)
        
        # Try Redis first if available
        if self.redis_client:
            try:
                serialized = json.dumps(value)
                return bool(self.redis_client.set(prefixed_key, serialized, ex=ttl))
            except Exception as e:
                logger.warning(f"Redis set error for key {key}: {e}")
        
        # Fallback to memory cache
        try:
            MEMORY_CACHE[prefixed_key] = {
                'value': value,
                'expires_at': time.time() + ttl if ttl else float('inf')
            }
            return True
        except Exception as e:
            logger.warning(f"Memory cache set error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        prefixed_key = self.get_key(key)
        success = False
        
        # Try Redis first if available
        if self.redis_client:
            try:
                success = bool(self.redis_client.delete(prefixed_key))
            except Exception as e:
                logger.warning(f"Redis delete error for key {key}: {e}")
        
        # Also check memory cache
        if prefixed_key in MEMORY_CACHE:
            del MEMORY_CACHE[prefixed_key]
            success = True
        
        return success
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern
        
        Args:
            pattern: Key pattern (e.g., "user:*")
            
        Returns:
            Number of keys deleted
        """
        prefixed_pattern = self.get_key(pattern)
        count = 0
        
        # Try Redis first if available
        if self.redis_client:
            try:
                # Get all keys matching pattern
                keys = self.redis_client.keys(prefixed_pattern)
                if keys:
                    count += self.redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"Redis delete pattern error for {pattern}: {e}")
        
        # Also check memory cache
        memory_keys = [k for k in MEMORY_CACHE.keys() if k.startswith(prefixed_pattern.replace('*', ''))]
        for k in memory_keys:
            del MEMORY_CACHE[k]
            count += 1
        
        return count
    
    def ttl(self, key: str) -> Optional[int]:
        """
        Get remaining time to live for a key
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds or None if key not found or no expiration
        """
        prefixed_key = self.get_key(key)
        
        # Try Redis first if available
        if self.redis_client:
            try:
                ttl = self.redis_client.ttl(prefixed_key)
                if ttl > 0:
                    return ttl
            except Exception as e:
                logger.warning(f"Redis TTL error for key {key}: {e}")
        
        # Fallback to memory cache
        if prefixed_key in MEMORY_CACHE:
            cache_item = MEMORY_CACHE[prefixed_key]
            expires_at = cache_item.get('expires_at')
            if expires_at != float('inf'):
                return max(0, int(expires_at - time.time()))
        
        return None


# Initialize global cache instance
cache = Cache()


def cached(ttl: int = 300, key_prefix: str = "", include_args: bool = True):
    """
    Cache decorator for functions
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Cache key prefix
        include_args: Whether to include function arguments in cache key
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Generate cache key
            if key_prefix:
                key_parts = [key_prefix]
            else:
                key_parts = [func.__module__, func.__name__]
            
            # Include arguments in cache key if requested
            if include_args:
                if args:
                    key_parts.append(str(args))
                if kwargs:
                    key_parts.append(str(sorted(kwargs.items())))
            
            # Create a hash of the key parts
            key = hashlib.md5(":".join(key_parts).encode()).hexdigest()
            
            # Check cache
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl=ttl)
            return result
        
        return wrapper
    
    return decorator


def invalidate_cache(key_prefix: str):
    """
    Invalidate cache for a given prefix
    
    Args:
        key_prefix: Cache key prefix
        
    Returns:
        Number of keys deleted
    """
    return cache.clear_pattern(f"{key_prefix}*")


def clear_user_cache(user_id: int) -> int:
    """
    Clear all cache entries for a user
    
    Args:
        user_id: User ID
        
    Returns:
        Number of keys deleted
    """
    return cache.clear_pattern(f"user:{user_id}:*")


def clear_course_cache(course_id: int) -> int:
    """
    Clear all cache entries for a course
    
    Args:
        course_id: Course ID
        
    Returns:
        Number of keys deleted
    """
    return cache.clear_pattern(f"course:{course_id}:*")