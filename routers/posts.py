from datetime import datetime, timezone
from typing import Annotated, Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, File, Form,  HTTPException, status, Depends, UploadFile
from pydantic import BaseModel, PositiveInt
from database.database import Db_dependency
from database.outputmodel import OutputPost
from routers.dependencies import User_auth
from utilities import post as postutils, attachments as attutils
from utilities.activity import logActivity
from configs.config_post import FeedCriteria, PostTag
from fastapi.responses import FileResponse

router = APIRouter()

class PostTextContent(BaseModel):
    title: str
    content: str
    tag: PostTag

    @classmethod
    def form(
        cls,
        title: Annotated[str, Form(min_length=1, max_length=255)],
        content: Annotated[str, Form(min_length=1)],
        tag: Annotated[PostTag, Form(min_length=1)]
    ):
        return cls(title=title, content=content, tag=tag)

@router.get("/", status_code=status.HTTP_200_OK)
async def get_newsfeed(this_user: User_auth, db: Db_dependency, criteria: FeedCriteria = 'latest', cursor: datetime | None = None, limit: PositiveInt = 15):
    """
    Get latest posts for user's feed.\n
    Return a list of post.
    """
    if cursor == None:
        cursor = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    feed = await postutils.queryFeed(db, cursor, criteria, limit)
    if feed is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Query parameter invalid")
    
    output = [await postutils.getOutputPost(this_user, p) for p in feed]
    return output

@router.get("/posts/{post_id}", status_code=status.HTTP_200_OK, response_model=OutputPost)
async def get_post(post_id: int, this_user: User_auth, db: Db_dependency):
    """
    Get the post by post_id
    """
    post = await postutils.getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return await postutils.getOutputPost(this_user, post)

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
        ats = await attutils.saveAttachments(db, attachments)
        if ats is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid file upload. Can upload at most 10 files per post. Only accept image with type jpg, png, gif with size < 5MB, and video with type mp4, mkv, mov, avi with size < 100MB")
    else:
        ats = None

    # Create a post object and get its post_id
    new_post = await postutils.createPost(db, this_user, text_content.title, text_content.content, text_content.tag, ats)

    return {
        "message": "Post created",
        "post_id": new_post.post_id,
    }

@router.put("/posts/{post_id}", status_code=status.HTTP_202_ACCEPTED)
async def edit_post(
    this_user: User_auth,
    db: Db_dependency,
    post_id: int,
    text_content: Annotated[PostTextContent, Depends(PostTextContent.form)],
    attachments_update: Annotated[str, Form()] = None,
    attachments: Optional[list[UploadFile]] = File(None)
):
    """
    Edit a post.
    if there are changes in attachments, please send the changes in `attachments_update` with syntax: "<change_type> <current_index> <new_position>"
    change_type can be:
    -   add: Add a new file to position `index`
    -   remove: Remove a file at position `index`
    -   move: Move a file from position `index` to `new_position`\n
    Then send new media files according to their indices.
    Don't need to provide <new_position> if change_type doesn't require.
    If there are multiple changes, separate them with commas only (without following space): <change1>,<change2>,...
    """
    post = await postutils.getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if attachments_update is not None:
        st = await attutils.editAttachments(db, post, attachments, attachments_update)
        if st == 1:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid file upload. Can upload at most 10 files per post. Only accept image with type jpg, png, gif with size < 5MB, and video with type mp4, mkv, mov, avi with size < 100MB")
        elif st == 2:
            raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Media indexed wrong")
        elif st == 3:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")

    # Update post content
    
    if post.author_id != this_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
    
    await postutils.updatePost(db, post, text_content.title, text_content.content, text_content.tag)

    return {
        "message": "Post updated successfully",
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