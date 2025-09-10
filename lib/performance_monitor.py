import time
import asyncio
from functools import wraps
from datetime import datetime

def measure_performance(component_name, logger):
    """
    Decorator factory with explicit logger.
    Logs format:
    [Metric] [Component] timestamp [INFO]: Function '...' executed ...
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = await func(*args, **kwargs)
                end_time = time.perf_counter()
                duration = end_time - start_time
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger.info(
                    f"Function '{func.__name__}' executed in {duration:.6f} seconds "
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
                logger.info(
                    f"Function '{func.__name__}' executed in {duration:.6f} seconds "
                    f"({duration * 1000:.2f} ms) at {timestamp}"
                )
                return result
            return sync_wrapper

    return decorator


class PerformanceTimer:
    """
    Context manager for manually measuring code block performance.
    """
    def __init__(self, component_name, block_name, logger):
        self.component_name = component_name
        self.block_name = block_name
        self.logger = logger

    def __enter__(self):
        self.start_time = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.perf_counter()
        duration = end_time - self.start_time
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(
            f"Code block '{self.block_name}' executed in {duration:.6f} seconds "
            f"({duration * 1000:.2f} ms) at {timestamp}"
        )
