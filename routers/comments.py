# from datetime import datetime, timezone
# from fastapi import APIRouter,  HTTPException, status, Depends, UploadFile
# from database.database import Db_dependency
# from database.models import User, Post, Attachment
# from database.outputmodel import PostWithAttachments, SimpleAttachment
# from typing import Annotated
# from utilities import account

# router = APIRouter()

# @router.get("posts/{post_id}/comments", status_code=status.HTTP_200_OK)
# async def getPostComments