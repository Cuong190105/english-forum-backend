from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo
from fastapi import APIRouter, status, HTTPException
from fastapi.responses import FileResponse
from database.models import Activity, User, Post, Notification
from database.outputmodel import OutputNotification
from database.database import Db_dependency
from routers.dependencies import User_auth
from utilities.attachments import getFile
from utilities.activity import getNotifications
router = APIRouter()

@router.get("/search", status_code=status.HTTP_200_OK)
async def search(this_user: User_auth, keyword: str, db: Db_dependency):
    if keyword is None or keyword == "":
        raise HTTPException("Keyword must not be null")
    
    users = db.query(User).filter(User.username.ilike(keyword)).all()
    post = db.query(Post).filter(Post.content.ilike(keyword)).all()

    return {
        "users": users,
        "posts": post
    }

@router.get("/notifications", status_code=status.HTTP_200_OK, response_model=list[OutputNotification])
async def get_notifications(this_user: User_auth, db: Db_dependency, cursor: datetime | None = None):
    if cursor == None:
        cursor = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return await getNotifications(this_user, db, cursor)

@router.get("/posts/{post_id}/exercise", status_code=status.HTTP_200_OK)
async def get_exercises(this_user: User_auth, post_id: int, db: Db_dependency):
    """
    Get exercises for practice based on post content using ✨AI
    """

    pass

@router.get("/download/{media_filename}")
async def download(db: Db_dependency, this_user: User_auth, media_filename: str):
    """
    Get media by its filename.
    """

    file = await getFile(db, media_filename)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested resource not found")
    
    return FileResponse(file)