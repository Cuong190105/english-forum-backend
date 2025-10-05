from datetime import datetime, timezone
from fastapi import APIRouter,  HTTPException, status, Depends, UploadFile
from database.database import Db_dependency
from database.models import User, Post, Attachment
from database.outputmodel import PostWithAttachments, SimpleAttachment
from typing import Annotated
from utilities import account

router = APIRouter()

@router.get("/", status_code=status.HTTP_200_OK)
async def get_newsfeed(this_user: Annotated[User, Depends(account.getUserFromToken)]):
    pass

@router.get("/posts/{post_id}", status_code=status.HTTP_200_OK, response_model=PostWithAttachments)
async def get_post(post_id: int, this_user: Annotated[User, Depends(account.getUserFromToken)], db: Db_dependency):
    post = db.query(Post).filter(
        Post.post_id == post_id,
        Post.is_deleted == False
    ).first()

    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found or deleted")
    attachments = db.query(Attachment).filter(Attachment.post_id == post_id).order_by(Attachment.index.asc()).all()
    simple_attachments = [
        SimpleAttachment(
            media_type=a.media_type,
            media_url=a.media_url,
            media_metadata=a.media_metadata,
            index=a.index
        ) for a in attachments
    ]
    output = PostWithAttachments(
        post_id=post.post_id,
        titile=post.title,
        content=post.content,
        vote=post.vote,
        comment_count=post.comment_count,
        created_at=post.created_at,
        is_modified=(post.updated_at > post.created_at),
        attachments=simple_attachments
    )
    return PostWithAttachments()

@router.post("/posts/upload", status_code=status.HTTP_201_CREATED)
async def upload_post(this_user: Annotated[User, Depends(account.getUserFromToken)], db: Db_dependency, title: str, content: str, attachments: list[UploadFile] | None = None):
    post = Post(author_id=this_user.user_id, title=title, content=content)
    db.add(post)
    db.commit()
    db.refresh(post)

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
    post = db.query(Post).filter(Post.post_id == post_id, Post.author_id == this_user.user_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed")
    post.title = title
    post.content = content
    post.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "message": "Post updated successfully"
    }

@router.delete("/posts/{post_id}", status_code=status.HTTP_200_OK)
async def delete_post(this_user: Annotated[User, Depends(account.getUserFromToken)], post_id: int, db: Db_dependency):
    post = db.query(Post).filter(Post.post_id == post_id, Post.author_id == this_user.user_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed")
    
    post.is_deleted = True
    post.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Post deleted"
    }