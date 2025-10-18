from datetime import datetime, timezone
from database.database import Db_dependency
from database.models import Post, Attachment, PostVote, User
from database.outputmodel import OutputPost, SimpleAttachment
from utilities import comment as cmtutils

async def getPost(post_id: int, db: Db_dependency):
    return db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()

async def getOutputPost(user: User, post_id: int, db: Db_dependency):
    post = await getPost(post_id, db)

    if post is None:
        return None
    
    user_vote = post.votes.filter(PostVote.user_id == user.user_id).first()
    if user_vote is None:
        vote_value = 0
    else:
        vote_value = user_vote.value

    # attachments = db.query(Attachment).filter(Attachment.post_id == post_id).order_by(Attachment.index.asc()).all()
    attachments = post.attachments

    simple_attachments = [
        SimpleAttachment(
            media_type=a.media_type,
            media_url=a.media_url,
            # media_metadata=str(a.media_metadata),
            media_metadata=a.media_metadata,
            index=a.index
        ) for a in attachments
    ]
    output = OutputPost(
        post_id=post.post_id,
        title=post.title,
        tag=post.tag,
        content=post.content,   
        vote_count=post.vote_count,
        user_vote=vote_value,
        comment_count=post.comment_count,
        created_at=post.created_at,
        is_modified=(post.updated_at > post.created_at),
        attachments=simple_attachments
    )
    return output

async def createPost(db: Db_dependency, author: User, title: str, content: str, tag: str):
    """
    Create a post.
    Params:
        db: Database session object
        author: User uploading post
        title: Post's title
        content: Post's content
        tag: Post's tag
    Returns:
        Post: a `Post` object for that post
    """

    # Create a post object and get its post_id
    now = datetime.now(timezone.utc)
    post = Post(
        author_id=author.user_id,
        title=title,
        content=content,
        tag=tag,
        created_at=now,
        updated_at=now
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    return post

async def updatePost(db: Db_dependency, post: Post, title: str, content: str, tag: str):
    """
    Update a post.

    Params:
        db: Database session object
        post: target post to update
        title: updated title
        content: updated content
        tag: updated tag

    Returns:
        None
    """
    post.title = title
    post.content = content
    post.tag = tag

    db.commit()

async def deletePost(db: Db_dependency, post: Post):
    """
    Mark a post and its related content as deleted.
    Params:
        db: Database session object
        post: target post
    Returns:
        None
    """

    post.is_deleted = True
    for cmt in post.comments:
        cmt.is_deleted = True
    for att in post.attachments:
        att.is_deleted = True
    db.commit()

async def votePost(db: Db_dependency, user: User, post: Post, value: int):
    """
    Change user vote on a post.
    Vote type can be -1, 0, 1 for downvote, no vote or upvote
    
    Params:
        db: Database session object
        user: The actor
        post: Target post
        value: Value of vote: -1, 0, 1

    Returns:
        bool: True if updated, else False if invalid value
    """

    VOTE_TYPE = ["novote", "upvote", "downvote"]

    # Check if value is valid
    if abs(value) > 1:
        return False

    vote = post.votes.filter(PostVote.user_id == user.user_id).first()
    if vote is None:
        vote = PostVote(user_id=user.user_id, value=0)

        # If this action is new, log the action
        # await logActivity(user_id, db, ActionType.VOTEPOST, VOTE_TYPE[value], vote.vote_id, post.author_id)
    
    post.vote_count += value - vote.value
    vote.value = value
    post.votes.append(vote)
    db.commit()

    return True
