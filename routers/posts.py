from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, File, Form,  HTTPException, Query, status, Depends, UploadFile
from pydantic import BaseModel, PositiveInt
from database.database import Db_dependency
from database.models import User, Post, Attachment, PostVote
from database.outputmodel import OutputPost, SimpleAttachment
from routers.dependencies import User_auth
from utilities import post as postutils
from utilities.attachments import getMetadata
from utilities.activity import logActivity
from configs.config_activity import ActionType
from configs.config_post import FeedCriteria

router = APIRouter()

class PostTextContent(BaseModel):
    title: str
    content: str
    tag: str

    @classmethod
    def form(
        cls,
        title: Annotated[str, Form(min_length=1)],
        content: Annotated[str, Form(min_length=1)],
        tag: Annotated[str, Form(min_length=1)]
    ):
        return cls(title=title, content=content, tag=tag)

@router.get("/", status_code=status.HTTP_200_OK)
async def get_newsfeed(this_user: User_auth, db: Db_dependency, criteria: FeedCriteria = 'latest', cursor: datetime = datetime.now(timezone.utc), limit: PositiveInt = 15):
    """
    Get latest posts for user's feed.\n
    Return a list of post.
    """

    feed = await postutils.queryFeed(db, cursor, criteria, limit)
    if feed is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Query parameter invalid")
    
    output = [await postutils.getOutputPost(this_user, p, db) for p in feed]
    return output

@router.get("/posts/{post_id}", status_code=status.HTTP_200_OK, response_model=OutputPost)
async def get_post(post_id: int, this_user: User_auth, db: Db_dependency):
    """
    Get the post by post_id
    """
    post = await postutils.getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return await postutils.getOutputPost(this_user, post, db)

@router.post("/posts/upload", status_code=status.HTTP_201_CREATED)
async def upload_post(
    this_user: User_auth, db: Db_dependency,
    text_content: Annotated[PostTextContent, Depends(PostTextContent.form)],
    attachments: Optional[list[UploadFile]] = File(None)
):
    """
    Upload a post
    """

    # Validate and store attachments
    if attachments is not None:
        ats = await postutils.saveAttachments(db, attachments)
        if ats is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid file type or size. Only accept image with type jpg, png, gif with size < 5MB, and video with type mp4, mkv, mov, avi with size < 100MB")
    else:
        ats = None

    # Create a post object and get its post_id
    new_post = await postutils.createPost(db, this_user, text_content.title, text_content.content, text_content.tag, ats)

    # Store the attachments

    await logActivity(this_user.user_id, db, ActionType.POST, new_post.content, new_post.post_id)

    return {
        "message": "Post created",
    }

@router.put("/posts/{post_id}", status_code=status.HTTP_202_ACCEPTED)
async def edit_post(
    this_user: User_auth,
    db: Db_dependency,
    post_id: int,
    text_content: Annotated[PostTextContent, Depends(PostTextContent.form)],
    attachments: Optional[list[UploadFile]] = File(None)
):
    """
    Edit a post
    """

    # Update post content
    post = await postutils.getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    if post.author_id != this_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
    
    await postutils.updatePost(db, post, text_content.title, text_content.content, text_content.tag)

    # TODO: Update post attachment
    for att in post.attachments:
        att.is_deleted=True
    
    # Store the attachments
    media_name = []
    if attachments is not None:
        for index in range(len(attachments)):
            # metadata = "str"
            # att = Attachment(
            #     post_id=post.post_id,
            #     media_type=attachments[index].content_type,
            #     media_metadata=attachments[index].headers,
            #     index=index
            # )
            # post.attachments.append(att)
            media_name.append(attachments[index].filename)
    db.commit()

    return {
        "message": "Post updated successfully",
        "filename": media_name,
    }

@router.delete("/posts/{post_id}", status_code=status.HTTP_200_OK)
async def delete_post(this_user: User_auth, post_id: int, db: Db_dependency):
    """
    Delete a post
    """
    post = await postutils.getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if post.author_id != this_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
    
    await postutils.deletePost(db, post)

    return {
        "message": "Post deleted"
    }

@router.post("/posts/{post_id}/vote", status_code=status.HTTP_200_OK)
async def vote_post(this_user: User_auth, post_id: int, vote_type: Annotated[int, Form()], db: Db_dependency):
    """
    Change user's vote of a post
    Vote type can be -1, 0, 1 for downvote, no vote or upvote
    """

    # Check if post exists
    post = await postutils.getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # Update vote count
    if not await postutils.votePost(db, this_user, post, vote_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid value")

    return {"message": "Voted"}