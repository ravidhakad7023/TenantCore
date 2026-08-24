import json
import redis
from typing import Optional, Any
from app.core.config import settings

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True
)

def get_cache(key: str) -> Optional[Any]:
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except redis.RedisError:
        return None

def set_cache(key: str, value: Any, ttl: int = 300) -> bool:
    try:
        data = json.dumps(value)
        redis_client.set(key, data, ex=ttl)
        return True
    except redis.RedisError:
        return False

def delete_cache(key: str) -> bool:
    try:
        redis_client.delete(key)
        return True
    except redis.RedisError:
        return False
