import json
import logging
from typing import Optional, Any
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        try:
            self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.client.ping()
            logger.info("Connected to Redis successfully.")
        except Exception as e:
            logger.warning(f"Could not connect to Redis at {settings.REDIS_URL}: {e}. Operating in graceful degradation mode.")
            self.client = None

    async def disconnect(self):
        if self.client:
            await self.client.close()

    async def publish(self, channel: str, message: Any):
        if not self.client:
            return
        try:
            payload = json.dumps(message) if not isinstance(message, str) else message
            await self.client.publish(channel, payload)
        except Exception as e:
            logger.error(f"Error publishing to Redis channel {channel}: {e}")

    async def check_rate_limit(self, key: str, max_requests: int, window_sec: int) -> bool:
        """Returns True if within limit, False if limit exceeded."""
        if not self.client:
            return True  # Fail open if Redis is down
        try:
            current = await self.client.incr(key)
            if current == 1:
                await self.client.expire(key, window_sec)
            return current <= max_requests
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            return True

redis_manager = RedisManager()
