from fastapi import HTTPException, Request
from app.core.redis import redis_client
from app.core.config import settings
import redis

class RateLimiter:
    def __init__(self, requests: int = None, window: int = None):
        self.requests = requests or settings.RATE_LIMIT_REQUESTS
        self.window = window or settings.RATE_LIMIT_WINDOW

    def __call__(self, request: Request):
        try:
            client_ip = request.client.host if request.client else "unknown"
            key = f"rate_limit:{client_ip}"
            
            # Simple fixed window implementation
            current_count = redis_client.get(key)
            if current_count and int(current_count) >= self.requests:
                raise HTTPException(status_code=429, detail="Too Many Requests")
                
            pipe = redis_client.pipeline()
            pipe.incr(key)
            if not current_count:
                pipe.expire(key, self.window)
            pipe.execute()
        except redis.RedisError:
            # If Redis is down, fail open to not block traffic unnecessarily,
            # or fail closed. We choose fail open.
            pass
