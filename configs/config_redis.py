from typing import Annotated
from fastapi.params import Depends
import redis.asyncio as aioredis
from dotenv import load_dotenv
import os
load_dotenv()

REDIS_CONNECTIONSTRING = os.getenv("REDIS_CONNECTIONSTRING")
def get_redis():
    with aioredis.from_url(REDIS_CONNECTIONSTRING, decode_responses=True) as redis_client:
        yield redis_client
Redis_dep = Annotated[aioredis.Redis, Depends(get_redis)]