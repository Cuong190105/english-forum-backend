from datetime import datetime, timezone
from fastapi import APIRouter,  HTTPException, status, Depends, UploadFile
from database.database import Db_dependency
from database.models import User, Post, Attachment
from database.outputmodel import PostWithAttachments, SimpleAttachment
from typing import Annotated
from utilities import account
from utilities.post import getPost, getOutputPost

router = APIRouter()

@router.get("/", status_code=status.HTTP_200_OK)
async def get_newsfeed(this_user: Annotated[User, Depends(account.getUserFromToken)]):
    """
    Get latest posts for user's feed.\n
    Return a list of post_id. To retrieve their content, make GET request for each post.
    """
    pass

@router.get("/posts/{post_id}", status_code=status.HTTP_200_OK, response_model=PostWithAttachments)
async def get_post(post_id: int, this_user: Annotated[User, Depends(account.getUserFromToken)], db: Db_dependency):
    """
    Get the post by post_id
    """
    post = await getOutputPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post

@router.post("/posts/upload", status_code=status.HTTP_201_CREATED)
async def upload_post(this_user: Annotated[User, Depends(account.getUserFromToken)], db: Db_dependency, title: str, content: str, attachments: list[UploadFile] | None = None):
    """
    Upload a post
    """

    # Create a post object and get its post_id
    now=datetime.now(timezone.utc)
    post = Post(
        author_id=this_user.user_id,
        title=title,
        content=content,
        created_at=now,
        updated_at=now
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    # Store the attachments
    for index in range(len(attachments)):
        # metadata = getMetadata(attachments[index])
        att = Attachment(
            post_id=post.post_id,
            media_type=attachments[index].content_type,
            media_metadata=attachments[index].headers,
            index=index
        )
        db.add(att)
    db.commit()

    return {
        "message": "Post created"
    }

@router.put("/posts/{post_id}", status_code=status.HTTP_202_ACCEPTED)
async def edit_post(this_user: Annotated[User, Depends(account.getUserFromToken)], db: Db_dependency, post_id: int, title: str, content: str, attachments: list[UploadFile] | None = None):
    """
    Edit a post
    """

    # Update post content
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed")
    post.title = title
    post.content = content
    post.updated_at = datetime.now(timezone.utc)
    
    # TODO: Update post attachment

    db.commit()

    return {
        "message": "Post updated successfully"
    }

@router.delete("/posts/{post_id}", status_code=status.HTTP_200_OK)
async def delete_post(this_user: Annotated[User, Depends(account.getUserFromToken)], post_id: int, db: Db_dependency):
    """
    Delete a post
    """
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed")
    
    post.is_deleted = True
    post.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Post deleted"
    }