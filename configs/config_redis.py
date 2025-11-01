import redis.asyncio as aioredis
from dotenv import load_dotenv
import os
load_dotenv()

REDIS_CONNECTIONSTRING = os.getenv("REDIS_CONNECTION_STRING", "redis://localhost:6379")

redis = aioredis.from_url(REDIS_CONNECTIONSTRING, decode_responses=True)