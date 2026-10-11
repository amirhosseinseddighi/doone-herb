import redis.asyncio as redis
from app.core.config import settings

pool = redis.ConnectionPool(
    host=settings.REDIS_URL.host,
    port=settings.REDIS_URL.port,
    decode_responses=True,
    max_connections=10,
    socket_timeout=5.0,
    socket_connect_timeout=3.0,
)

redis_client = redis.Redis(connection_pool=pool)