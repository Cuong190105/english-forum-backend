from datetime import datetime, timezone
from fastapi import APIRouter,  HTTPException, status, Depends, UploadFile
from configs.config_activity import ActionType
from database.database import Db_dependency
from database.models import User, Comment, CommentVote
from database.outputmodel import SimpleComment
from typing import Annotated
from routers.dependencies import User_auth
from utilities.activity import logActivity
from utilities.post import getPost

router = APIRouter()

@router.get("posts/{post_id}/comments", status_code=status.HTTP_200_OK, response_model=list[SimpleComment])
async def get_post_comments(this_user: User_auth, post_id: int, db: Db_dependency):
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
async def upload_comment(this_user: User_auth, post_id: int, content: str, db: Db_dependency, reply_comment_id: int = None):
    """
    Upload a comment for a post
    """

    # Get the post
    post = await getPost(post_id, db)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    if content is None or content == "":
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Comment should not be empty")
    
    # Create comment object and store in db
    new_comment = Comment(
        author_id=this_user.user_id,
        content=content
    )

    # Save comment and create notification
    acttype = ActionType.COMMENT
    target_noti_id = post.author_id
    
    if reply_comment_id is not None:
        reply_to = db.query(Comment).filter(Comment.comment_id == reply_comment_id, Comment.is_deleted == False).first()
        if reply_to is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

        new_comment.reply_to_id = reply_comment_id
        acttype = ActionType.REPLY
        target_noti_id = reply_to.author_id

    post.comments.append(new_comment)
    db.commit()
    db.refresh(new_comment)


    await logActivity(this_user.user_id, acttype, content, new_comment.comment_id, db, target_noti_id)

    return {
        "message": "Comment Uploaded"
    }

@router.put("/comments/{comment_id}", status_code=status.HTTP_202_ACCEPTED)
async def edit_comment(this_user: User_auth, comment_id: int, content: str, db: Db_dependency):
    cmt = db.query(Comment).filter(Comment.comment_id == comment_id, Comment.is_deleted == False).first()
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    if content is None or content == "":
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Comment should not be empty")
    
    cmt.content = content
    db.commit()

    return {
        "message": "Comment updated"
    }

@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(this_user: User_auth, comment_id: int, db: Db_dependency):
    """
    Delete a comment
    """
    cmt = db.query(Comment).filter(Comment.comment_id == comment_id, Comment.is_deleted == False).first()
    if cmt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    cmt.is_deleted = True
    db.commit()

    return {
        "message": "Comment deleted"
    }

@router.post("/comments/{comment_id}/vote", status_code=status.HTTP_200_OK)
async def vote_comment(this_user: User_auth, comment_id: int, vote_type: int, db: Db_dependency):
    """
    Change user's vote of a comment
    Vote type can be -1, 0, 1 for downvote, no vote or upvote
    """

    VOTE_TYPE = ["novote", "upvote", "downvote"]

    # Check if value is valid
    if vote_type not in [-1, 0, 1]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid value")

    # Check if comment exists
    comment = db.query(Comment).filter(Comment.comment_id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    # Update vote count
    vote = comment.votes.filter(CommentVote.user_id == this_user.user_id).first()
    if vote is None:
        vote = CommentVote(user_id=this_user.user_id, comment_id=comment_id, value=0)
        db.add(vote)
        db.commit()
        db.refresh(vote)

        # If this action is new, log the action
        await logActivity(this_user.user_id, db, ActionType.VOTECOMMENT, VOTE_TYPE[vote_type], vote.vote_id, comment.author_id)
    
    comment.vote_count += vote_type - vote.value
    vote.value = vote_type
    db.commit()


    return {"message": "Voted"}