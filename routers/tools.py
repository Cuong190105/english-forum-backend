from typing import Annotated
from fastapi import APIRouter, status, HTTPException
from database.models import Activity, User, Post, Notification
from database.outputmodel import OutputNotification
from database.database import Db_dependency
from utilities.account import User_auth
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

@router.get("/notifications", status_code=status.HTTP_200_OK, response_model=OutputNotification)
async def get_notifications(this_user: User_auth, db: Db_dependency, start: int = 0):
    NOTI_PAGE_LIMIT = 10
    noti = db.query(Notification)\
        .filter(Notification.user_id == this_user.user_id, Notification.is_deleted == False)\
        .order_by(Notification.created_at.desc())\
        .limit(NOTI_PAGE_LIMIT).offset(start)\
        .all()

    output = []
    for n in noti:
        activity: Activity = n.activity
        output.append(OutputNotification(
            actor_id=activity.actor_id,
            action_type=activity.action,
            action_id=activity.target_id,
            is_read=n.is_read,
            brief=n.content
        ))
    return noti

@router.get("/posts/{post_id}/exercise", status_code=status.HTTP_200_OK)
async def get_exercises(this_user: User_auth, post_id: int, db: Db_dependency):
    """
    Get exercises for practice based on post content using ✨AI
    """

    pass