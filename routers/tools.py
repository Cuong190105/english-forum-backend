from typing import Annotated
from fastapi import APIRouter, status, HTTPException
from database.models import User, Post
from database.database import Db_dependency
from utilities import account
router = APIRouter()

@router.get("/search", status_code=status.HTTP_200_OK)
async def search(this_user: Annotated[User, account.getUserFromToken], keyword: str, db: Db_dependency):
    if keyword is None or keyword == "":
        raise HTTPException("Keyword must not be null")
    
    users = db.query(User).filter(User.username.ilike(keyword)).all()
    post = db.query(Post).filter(Post.content)

    return {
        "users": users,
        "posts": post
    }

@router.get("/notifications", status_code=status.HTTP_200_OK)
async def get_notifications(this_user: Annotated[User, account.getUserFromToken]):
    pass