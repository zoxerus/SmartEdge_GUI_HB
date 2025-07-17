import time
import logging
import asyncio
from functools import wraps
from datetime import datetime
from lib.logger_utils import get_logger

def measure_performance(component_name, logger=None):
    """
    Decorator to measure execution time of sync or async functions.
    Logs to the provided logger or falls back to a default logger.
    """
    log = logger or get_logger("performance")

    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = await func(*args, **kwargs)
                end_time = time.perf_counter()
                duration = end_time - start_time
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log.info(
                    f"[Performance] [{component_name}] Function '{func.__name__}' "
                    f"executed in {duration:.6f} seconds "
                    f"({duration * 1000:.2f} ms) at {timestamp}"
                )
                return result
            return async_wrapper

        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = func(*args, **kwargs)
                end_time = time.perf_counter()
                duration = end_time - start_time
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log.info(
                    f"[Performance] [{component_name}] Function '{func.__name__}' "
                    f"executed in {duration:.6f} seconds "
                    f"({duration * 1000:.2f} ms) at {timestamp}"
                )
                return result
            return sync_wrapper
    return decorator


class PerformanceTimer:
    """
    Context manager for timing code blocks.
    Usage:
        with PerformanceTimer("Coordinator", "Some Block", logger):
            ...
    """
    def __init__(self, component_name, block_name, logger=None):
        self.component_name = component_name
        self.block_name = block_name
        self.logger = logger or get_logger("performance")

    def __enter__(self):
        self.start_time = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.perf_counter()
        duration = end_time - self.start_time
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.logger.info(
            f"[Performance] [{self.component_name}] Code block '{self.block_name}' "
            f"executed in {duration:.6f} seconds "
            f"({duration * 1000:.2f} ms) at {timestamp}"
        )
