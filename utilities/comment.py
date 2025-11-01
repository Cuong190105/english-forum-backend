from datetime import datetime
from database.database import Db_dependency
from database.models import Post, Comment, CommentVote, User
from database.outputmodel import OutputComment
from utilities.activity import logActivity, publishPostEvent

async def getComments(db: Db_dependency, post: Post, user: User, offset: int, limit: int):
    """
    Get comments from a post.

    Params:
        db: Database session object.
        post: Post.
        offset: Skip top `offset` comments.
        limit: Number of comments to get.

    Returns:
        list[SimpleComment]: Comment list
    """

    # Query comments as requested
    comments = db.query(Comment).filter(
        Comment.post_id == post.post_id,
        Comment.is_deleted == False
    ).offset(offset).limit(limit).all()


    # Simplify output data.
    output = [await getOutputComment(user, c) for c in comments]

    # Sort the comments according to the votes
    output.sort(key=lambda x: x.vote_count, reverse=True)
    return output

async def getOutputComment(user: User, comment: Comment):
    """
    Add more user related data to regular comments.

    Params:
        comment: Comment object
        user: The actor

    Returns:
        OutputComment: Converted comment
    """

    user_vote = comment.votes.filter(CommentVote.user_id == user.user_id).first()
    if user_vote is None:
        vote_value = 0
    else:
        vote_value = user_vote.value

    return OutputComment(
        author_username=comment.author.username,
        author_avatar=comment.author.avatar_filename,
        post_id=comment.post_id,
        comment_id=comment.comment_id,
        content=comment.content,
        reply_to_id=comment.reply_to_id,
        vote_count=comment.vote_count,
        user_vote=vote_value,
        created_at=comment.created_at,
        is_modified=(comment.updated_at > comment.created_at)
    )

async def getCommentById(db: Db_dependency, comment_id: int):
    """
    Get a comment by id.

    Params:
        db: Database session object
        comment_id: Comment id

    Returns:
        Optional[Comment]: Comment if found, else None
    """

    return db.query(Comment).filter(Comment.comment_id == comment_id, Comment.is_deleted == False).first()

async def createComment(db: Db_dependency, user: User, post: Post, content: str, reply_to_id: int | None):
    """
    Create a comment on a post. Also trigger notification on target user: Post Author on normal comment, Target comment Author on reply.

    Params:
        db: Database session object
        user: The author
        post: Target post
        content: Comment text
    
    Returns:
        Optional[Comment]: New comment. If content is empty, return None
    """

    if content is None or content == "":
        return None

    comment = Comment(
        author_id=user.user_id,
        content=content,
        reply_to_id=reply_to_id
    )

    post.comments.append(comment)
    db.commit()
    db.refresh(comment)

    await publishPostEvent(comment.post_id, {
        "message": f"New comment",
        "comment_id": comment.comment_id,
        "reply_to_id": comment.reply_to_id,
    })

    return comment

async def updateComment(db: Db_dependency, comment: Comment, content: str):
    """
    Modify a comment.

    Params:
        db: Database session object
        comment: Comment need editing
        content: new updated content
    
    Returns:
        bool: True if updated, else False 
    """

    if content is None or content == "":
        return False
    
    comment.content = content
    db.commit()

    return True

async def deleteComment(db: Db_dependency, comment: Comment):
    """
    Delete a comment.

    Params:
        db: Database session object
        content: Comment text
    
    Returns:
        bool: True if updated, else False
    """
    
    comment.is_deleted = True
    db.commit()

    return True

async def voteComment(db: Db_dependency, user: User, comment: Comment, value: int):
    """
    Change user vote on a comment.
    Vote type can be -1, 0, 1 for downvote, no vote or upvote
    
    Params:
        db: Database session object
        user: The actor
        comment: Target comment
        value: Value of vote: -1, 0, 1

    Returns:
        bool: True if updated, else False if invalid value. 
    """

    VOTE_TYPE = ["novote", "upvote", "downvote"]

    # Check if value is valid
    if abs(value) > 1:
        return False

    is_new = False
    vote = comment.votes.filter(CommentVote.user_id == user.user_id).first()
    if vote is None:
        vote = CommentVote(user_id=user.user_id, value=0)

        # If this action is new, log the action
        is_new = True
    
    if vote.value != value:
        comment.vote_count += value - vote.value
        vote.value = value
        comment.votes.append(vote)
        db.commit()
        db.refresh(vote)

        if is_new:
            await logActivity(user.user_id, db, 'vote_comment', str(value), vote.vote_id, 'comment', comment.comment_id, comment.author_id)

        await publishPostEvent(comment.post_id, {
            "message": f"New vote comment",
            "comment_id": comment.comment_id,
            "total_value": comment.vote_count,
        })

    return True

async def getUserComments(this_user: User, user: User, cursor: datetime):
    """
    Get user's comments

    Parans:
        this_user: User requesting
        user: Target user
        cursor: Get all comments up to this timestamp
    
    Returns:
        list[OutputComment]: All processed comments.
    """
    LIMIT = 10
    comments = user.comments.filter(Comment.is_deleted == False, Comment.created_at < cursor).limit(LIMIT).all()
    return [await getOutputComment(this_user, c) for c in comments]