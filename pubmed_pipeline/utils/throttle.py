"""
Rate limiting and retry utilities for NCBI E-utilities.
"""

import time
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, qps: float = 3.0):
        self.min_interval = 1.0 / qps
        self.last_request = 0.0
    
    def wait(self):
        now = time.time()
        elapsed = now - self.last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request = time.time()
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)
        return wrapper

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor ** attempt)
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed: {e}")
            raise last_exception
        return wrapper
    return decorator

class ProgressTracker:
    def __init__(self, total: int, name: str = "Progress"):
        self.total = total
        self.current = 0
        self.name = name
        self.start_time = time.time()
    
    def update(self, n: int = 1):
        self.current += n
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        pct = (self.current / self.total * 100) if self.total > 0 else 0
        eta = (self.total - self.current) / rate if rate > 0 else 0
        print(f"\r{self.name}: {self.current}/{self.total} ({pct:.1f}%) | {rate:.1f}/s | ETA: {eta:.0f}s", end="", flush=True)
    
    def finish(self):
        elapsed = time.time() - self.start_time
        print(f"\n{self.name}: Completed {self.current} in {elapsed:.1f}s")
