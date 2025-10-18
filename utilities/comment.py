from database.database import Db_dependency
from database.models import Post, Comment, CommentVote, User
from database.outputmodel import SimpleComment

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
    output = [getOutputComments(c, user) for c in comments]

    # Sort the comments according to the votes
    output.sort(key=lambda x: x.vote_count, reverse=True)
    return output

def getOutputComments(comment: Comment, user: User):
    """
    Convert a Comment to SimpleComment.

    Params:
        comment: Comment object
        user: The actor

    Returns:
        SimpleComment: Converted comment
    """

    user_vote = comment.votes.filter(CommentVote.user_id == user.user_id).first()
    if user_vote is None:
        vote_value = 0
    else:
        vote_value = user_vote.value

    return SimpleComment(
        author_id=comment.author_id,
        content=comment.content,
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

    # TODO: Log activity and notify related user.

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
        bool: True if updated, else False if invalid value
    """

    VOTE_TYPE = ["novote", "upvote", "downvote"]

    # Check if value is valid
    if abs(value) > 1:
        return False

    vote = comment.votes.filter(CommentVote.user_id == user.user_id).first()
    if vote is None:
        vote = CommentVote(user_id=user.user_id, value=0)

        # If this action is new, log the action
        # await logActivity(user_id, db, ActionType.VOTECOMMENT, VOTE_TYPE[value], vote.vote_id, comment.author_id)
    
    comment.vote_count += value - vote.value
    vote.value = value
    comment.votes.append(vote)
    db.commit()

    return True
