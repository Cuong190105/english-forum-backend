from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, File, Form,  HTTPException, Query, status, Depends, UploadFile
from pydantic import BaseModel
from database.database import Db_dependency
from database.models import User, Post, Attachment, PostVote
from database.outputmodel import PostWithAttachments, SimpleAttachment
from utilities.account import User_auth
from utilities.post import getPost, getOutputPost
from utilities.attachments import getMetadata

router = APIRouter()

class PostTextContent(BaseModel):
    title: Annotated[str, Query(min_length=1, max_length=100)]
    content: Annotated[str, Query(min_length=1)]
    tag: Annotated[str, Query(min_length=1)]

    @classmethod
    def form(
        cls,
        title: Annotated[str, Form()],
        content: Annotated[str, Form()],
        tag: Annotated[str, Form()]
    ):
        return cls(title=title, content=content, tag=tag)

@router.get("/", status_code=status.HTTP_200_OK)
async def get_newsfeed(this_user: User_auth):
    """
    Get latest posts for user's feed.\n
    Return a list of post_id. To retrieve their content, make GET request for each post.
    """
    pass

@router.get("/posts/{post_id}", status_code=status.HTTP_200_OK, response_model=PostWithAttachments)
async def get_post(post_id: int, this_user: User_auth, db: Db_dependency):
    """
    Get the post by post_id
    """
    post = await getOutputPost(this_user.user_id, post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post

@router.post("/posts/upload", status_code=status.HTTP_201_CREATED)
async def upload_post(
    this_user: User_auth, db: Db_dependency,
    text_content: Annotated[PostTextContent, Depends(PostTextContent.form)],
    attachments: Optional[list[UploadFile]] = File(None)
):
    """
    Upload a post
    """

    # Create a post object and get its post_id
    now=datetime.now(timezone.utc)
    post = Post(
        author_id=this_user.user_id,
        title=text_content.title,
        content=text_content.content,
        tag=text_content.tag,
        created_at=now,
        updated_at=now
    )

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
    else:
        print("none")
    db.add(post)
    db.commit()

    return {
        "message": "Post created",
        "filename": media_name,
    }

@router.put("/posts/{post_id}", status_code=status.HTTP_202_ACCEPTED)
async def edit_post(
    this_user: User_auth,
    db: Db_dependency,
    post_id: int,
    text_content: Annotated[PostTextContent, Depends(PostTextContent.form)],
    attachments: Optional[list[UploadFile]] = File(None)):
    """
    Edit a post
    """

    # Update post content
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed")
    post.title = text_content.title
    post.content = text_content.content
    post.tag = text_content.tag
    post.updated_at = datetime.now(timezone.utc)
    
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
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed")
    
    now = datetime.now(timezone.utc)
    post.is_deleted = True
    post.updated_at = now
    for cmt in post.comments:
        cmt.is_deleted = True
        cmt.updated_at = now
    for att in post.attachments:
        att.is_deleted = True
    db.commit()

    return {
        "message": "Post deleted"
    }

@router.post("/posts/{post_id}/vote", status_code=status.HTTP_200_OK)
async def vote_post(this_user: User_auth, post_id: int, vote_type: int, db: Db_dependency):
    """
    Change user's vote of a post
    Vote type can be -1, 0, 1 for downvote, no vote or upvote
    """

    # Check if value is valid
    if vote_type not in [-1, 0, 1]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid value")

    # Check if post exists
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # Update vote count
    vote = post.votes.filter(PostVote.user_id == this_user.user_id).first()
    if vote is None:
        vote = PostVote(user_id=this_user.user_id, post_id=post_id, value=0)
        db.add(vote)
    post.vote_count += vote_type - vote.value
    vote.value = vote_type
    db.commit()

    return {"message": "Voted"}
