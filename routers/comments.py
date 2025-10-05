from datetime import datetime, timezone
from fastapi import APIRouter,  HTTPException, status, Depends, UploadFile
from database.database import Db_dependency
from database.models import User, Comment
from database.outputmodel import SimpleComment
from typing import Annotated
from utilities.account import getUserFromToken
from utilities.post import getPost

router = APIRouter()

@router.get("posts/{post_id}/comments", status_code=status.HTTP_200_OK, response_model=list[SimpleComment])
async def get_post_comments(this_user: Annotated[User, Depends(getUserFromToken)], post_id: int, db: Db_dependency):
    """
    Get all comments of a post.
    """

    # Get the post
    post = getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # Get all comments of the post
    comments = []
    for cmt in post.comments:
        if not cmt.is_deleted:
            comments.append(SimpleComment(
                author_id=cmt.author_id,
                content=cmt.content,
                vote=cmt.vote,
                created_at=cmt.created_at,
                is_modified=(cmt.updated_at > cmt.created_at)
            ))

    # Sort the comments according to the votes
    comments.sort(key=lambda x: x.vote, reverse=True)
    return comments

@router.post("/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
async def upload_comment(this_user: Annotated[User, Depends(getUserFromToken)], post_id: int, content: str, db: Db_dependency):
    """
    Upload a comment for a post
    """

    # Get the post
    post = getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    if content is None or content == "":
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Comment should not be empty")
    
    new_comment = Comment(
        author_id=this_user.user_id,
        content=content
    )

    new_comment.post = post
    db.commit()
    return {
        "message": "Comment Uploaded"
    }

@router.put("/comments/{comment_id}", status_code=status.HTTP_202_ACCEPTED)
async def edit_comment(this_user: Annotated[User, Depends(getUserFromToken)], comment_id: int, content: str, db: Db_dependency):
    cmt = db.query(Comment).filter(Comment.comment_id == comment_id, Comment.is_deleted == False).first()
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    cmt.content = content
    db.commit()

    return {
        "message": "Comment updated"
    }

@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(this_user: Annotated[User, Depends(getUserFromToken)], comment_id: int, content: str, db: Db_dependency):
    cmt = db.query(Comment).filter(Comment.comment_id == comment_id, Comment.is_deleted == False).first()
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    cmt.is_deleted = True
    db.commit()

    return {
        "message": "Comment deleted"
    }