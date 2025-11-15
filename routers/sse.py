import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from database.database import Db_dependency
from routers.dependencies import User_auth
from configs.config_redis import Redis_dep
from utilities.activity import eventStream

router = APIRouter()

@router.get("/sse/notifications")
async def sse_notifications(this_user: User_auth, redis: Redis_dep, request: Request):
    """
    Server-Sent Events endpoint for notifications.
    """

    return StreamingResponse(eventStream(redis, "noti", this_user.user_id, request), media_type="text/event-stream")

@router.get("/sse/post/{post_id}")
async def sse_post_event(this_user: User_auth, post_id: int, redis: Redis_dep, request: Request):
    """
    Server-Sent Events endpoint for post events.
    """
    return StreamingResponse(eventStream(redis, "post", post_id, request), media_type="text/event-stream")
