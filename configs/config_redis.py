import redis.asyncio as aioredis
from dotenv import load_dotenv
import os
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT)
