from fastapi import APIRouter,  HTTPException, status, Depends
from pydantic import BaseModel
from database.database import Db_dependency
from database import models
from typing import Annotated
from sqlalchemy import func
from .auth import getUserFromToken
import jwt
router = APIRouter()

class User(BaseModel):
    user_id: int
    username: str
    email: str
    bio: str | None
    avatar_url: str | None
    email_verified_at: str
    created_at: str
    updated_at: str
    
@router.get("/users", status_code=status.HTTP_200_OK)
async def getCurrentUser(this_user: Annotated[User, Depends(getUserFromToken)]):
    return this_user