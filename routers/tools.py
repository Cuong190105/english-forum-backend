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
from utilities.activity import getNotifications, markAsRead
from utilities import tool
router = APIRouter()

@router.get("/search", status_code=status.HTTP_200_OK)
async def search(this_user: User_auth, keyword: str, db: Db_dependency):
    if keyword is None or keyword == "":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keyword must not be null")
    
    result = await tool.search(db, this_user, keyword)

    return result

@router.get("/notifications", status_code=status.HTTP_200_OK, response_model=list[OutputNotification])
async def get_notifications(this_user: User_auth, db: Db_dependency, cursor: datetime | None = None, since_id: int = 0):
    if cursor == None:
        cursor = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return await getNotifications(this_user, db, cursor, since_id)

@router.put("/notifications/{notification_id}", status_code=status.HTTP_200_OK)
async def mark_as_read(this_user: User_auth, db: Db_dependency, notification_id: int):
    if not await markAsRead(db, this_user, notification_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to mark")

    return {
        "message": "Done"
    }

@router.get("/download/{media_filename}")
async def download(db: Db_dependency, this_user: User_auth, media_filename: str):
    """
    Get media by its filename.
    """

    file = await getFile(db, media_filename)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested resource not found")
    
    return FileResponse(file)