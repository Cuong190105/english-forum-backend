from fastapi import APIRouter, Form,  HTTPException, status
from database.database import Db_dependency
from database.outputmodel import OutputComment
from typing import Annotated
from routers.dependencies import User_auth
from utilities.activity import logActivity
from utilities.post import getPost
from utilities import comment as cmtutils

router = APIRouter()

@router.get("/posts/{post_id}/comments", status_code=status.HTTP_200_OK, response_model=list[OutputComment])
async def get_post_comments(db: Db_dependency, this_user: User_auth, post_id: int, offset: int = 0, limit: int = 100):
    """
    Get all comments of a post.
    """

    # Get the post
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # Get all comments of the post
    comments = await cmtutils.getComments(db, post, this_user, offset, limit)
    return comments

@router.post("/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
async def upload_comment(this_user: User_auth, post_id: int, content: Annotated[str, Form(min_length=1)], db: Db_dependency, reply_comment_id: int | None = None):
    """
    Upload a comment for a post
    """

    # Get the post
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    target = None
    if reply_comment_id is not None:
        target = await cmtutils.getCommentById(db, reply_comment_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replied to non-existent comment")
        if target.post_id != post.post_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reply comment does not belong to the same post")
            
    
    # Create comment object
    comment = await cmtutils.createComment(db, this_user, post, content, reply_comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment cannot be blank")
     
    if reply_comment_id is not None:
        await logActivity(this_user.user_id, db, 'reply', comment.content, comment.comment_id, 'comment', target.comment_id, target.author.user_id)
    else:
        await logActivity(this_user.user_id, db, 'comment', comment.content, comment.comment_id, 'post', post.post_id, post.author_id)

    return {
        "message": "Comment Uploaded",
        "comment_id": comment.comment_id,
    }

@router.get("/comments/{comment_id}", status_code=status.HTTP_202_ACCEPTED, response_model=OutputComment)
async def get_comment_by_id(this_user: User_auth, comment_id: int, db: Db_dependency):
    cmt = await cmtutils.getCommentById(db, comment_id)
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    return await cmtutils.getOutputComment(this_user, cmt)

@router.put("/comments/{comment_id}", status_code=status.HTTP_202_ACCEPTED)
async def edit_comment(this_user: User_auth, comment_id: int, content: Annotated[str, Form(min_length=1)], db: Db_dependency):
    cmt = await cmtutils.getCommentById(db, comment_id)
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    if cmt.author_id != this_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")

    if not await cmtutils.updateComment(db, cmt, content):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment cannot be blank")

    return {
        "message": "Comment updated"
    }

@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(this_user: User_auth, comment_id: int, db: Db_dependency):
    """
    Delete a comment
    """
    cmt = await cmtutils.getCommentById(db, comment_id)
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    if cmt.author_id != this_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
    
    await cmtutils.deleteComment(db, cmt)

    return {
        "message": "Comment deleted"
    }

@router.post("/comments/{comment_id}/vote", status_code=status.HTTP_200_OK)
async def vote_comment(this_user: User_auth, comment_id: int, vote_type: int, db: Db_dependency):
    """
    Change user's vote of a comment
    Vote type can be -1, 0, 1 for downvote, no vote or upvote
    """

    # Check if comment exists
    cmt = await cmtutils.getCommentById(db, comment_id)
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    # Update vote count
    if not await cmtutils.voteComment(db, this_user, cmt, vote_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid value")

    return {"message": "Voted"}