from datetime import datetime, timezone
import os
import typing
import uuid
from fastapi import UploadFile
from sqlalchemy import func
from database.database import Db_dependency
from database.models import Post, Attachment, PostVote, User
from database.outputmodel import OutputPost, SimpleAttachment
from utilities import comment as cmtutils
from configs.config_post import FeedCriteria, FileChange
from configs.config_validation import FileRule
from utilities.activity import logActivity

async def getPost(post_id: int, db: Db_dependency):
    """
    Get a post by id.

    Params:
        post_id: Id of post
        db: Database session object

    Returns:
        Optional[models.Post]: The requested post if found, else None
    """
    return db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()

async def queryFeed(db: Db_dependency, cursor: datetime, criteria: FeedCriteria, limit: int):
    """
    Get a list of posts for newsfeed.

    Params:
        db: Database session object
        cursor: A timestamp that queried posts are created before that
        criteria: Specify how the posts are queried, by topic, trending, or time
        limit: The number of posts to get.

    Returns:
        Optional[list[models.Post]]: The requested posts. If criteria is invalid, return None
    """
    if criteria not in typing.get_args(FeedCriteria) or limit < 1:
        return None
    query = db.query(Post)

    if criteria == 'trending':
        query = query.order_by(((Post.vote_count + Post.comment_count * 2) / (func.now() - Post.created_at + 1)).desc())
    
    elif criteria != 'latest':
        query = query.filter(Post.tag == criteria)
    
    posts = query.filter(Post.created_at < cursor).order_by(Post.created_at.desc()).limit(limit).all()
    return posts

async def getOutputPost(user: User, post: Post):
    if post is None:
        return None
    
    user_vote = post.votes.filter(PostVote.user_id == user.user_id).first()
    if user_vote is None:
        vote_value = 0
    else:
        vote_value = user_vote.value

    attachments = post.attachments

    simple_attachments = [
        SimpleAttachment(
            media_type=a.media_type,
            media_filename=a.media_filename,
            media_metadata=a.media_metadata,
            index=a.index
        ) for a in attachments
    ]
    output = OutputPost(
        post_id=post.post_id,
        author_username=post.author.username,
        author_avatar=post.author.avatar_filename,
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

async def createPost(db: Db_dependency, author: User, title: str, content: str, tag: str, ats: list[Attachment] = None):
    """
    Create a post.
    Params:
        db: Database session object
        author: User uploading post
        title: Post's title
        content: Post's content
        tag: Post's tag
        ats: List of Attachment objects
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

    if ats is not None:
        post.attachments.extend(ats)

    db.add(post)
    db.commit()
    db.refresh(post)

    await logActivity(author.user_id, db, 'post', content, post.post_id, 'post', post.post_id, author.user_id)


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

    is_new = False
    vote = post.votes.filter(PostVote.user_id == user.user_id).first()
    if vote is None:
        vote = PostVote(user_id=user.user_id, value=0)

        # If this action is new, log the action
        is_new = True
    
    post.vote_count += value - vote.value
    vote.value = value
    post.votes.append(vote)
    db.commit()
    db.refresh(vote)
    
    if is_new:
        await logActivity(user.user_id, db, 'vote_post', VOTE_TYPE[value], vote.vote_id, 'post', post.post_id, post.author_id)

    return True

async def getUserPosts(this_user: User, user: User, cursor: datetime):
    """
    Get user's posts

    Parans:
        this_user: User requesting
        user: Target user
        cursor: Get all posts up to this timestamp
    
    Returns:
        list[OutputPost]: All processed posts.
    """
    LIMIT = 10
    posts = user.posts.filter(Post.is_deleted == False, Post.created_at < cursor).limit(LIMIT).all()
    return [await getOutputPost(this_user, p) for p in posts]