import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from database.database import Db_dependency
from routers.dependencies import User_auth
from utilities.activity import eventStream

router = APIRouter()

@router.get("/sse/notifications")
async def sse_notifications(this_user: User_auth):
    """
    Server-Sent Events endpoint for notifications.
    """

    return StreamingResponse(eventStream("noti", this_user.user_id), media_type="text/event-stream")

@router.get("/sse/post/{post_id}")
async def sse_post_event(this_user: User_auth, post_id: int):
    """
    Server-Sent Events endpoint for post events.
    """
    return StreamingResponse(eventStream("post", post_id), media_type="text/event-stream")
