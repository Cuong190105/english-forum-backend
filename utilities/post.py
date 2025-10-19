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
from configs.config_post import FeedCriteria
from configs.config_validation import FileRule

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

async def getOutputPost(user: User, post: Post, db: Db_dependency):
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

async def validateSize(file: UploadFile):
    """
    Validate a file by type and size.
    
    Params:
        file: File need validating

    Returns:
        bool: True if pass, else False
    """
    ext = os.path.splitext(file.filename)[1]
    limitSize = 0
    if ext in FileRule.VALID_IMAGE_FILE_TYPES:
        limitSize = FileRule.IMAGE_MAX_SIZE_MB
    elif ext in FileRule.VALID_VIDEO_FILE_TYPES:
        limitSize = FileRule.VIDEO_MAX_SIZE_MB
    else:
        return False
    
    total_size = 0
    CHUNK_SIZE = 1024 * 1024
    while chunk := await file.read(CHUNK_SIZE):
        total_size += len(chunk) / CHUNK_SIZE
        if total_size >= limitSize:
            return False
    file.file.seek(0)
    return True


async def saveAttachments(db: Db_dependency, attachments: list[UploadFile]):
    """
    Validate and store attachments.

    Params:
        db: Database session object
        attachments: List of Files uploaded

    Returns:
        Optional[list[Attachment]]: List of Attachment metadata objects. None if one of the attachment fails the validation.  
    """
    # Validate files
    for file in attachments:
        if not await validateSize(file):
            return None
    
    # Store files
    os.makedirs("storage/public", exist_ok=True)
    idx = 0
    try:
        saved = []
        for file in attachments:
            ext = os.path.splitext(file.filename)[1]
            
            filename = f"{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}_{uuid.uuid4().hex}{ext}"
            path = f"storage/public/{filename}"
            with open(path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    buffer.write(chunk)

            attachment = Attachment(
                media_type=file.content_type,
                media_metadata="",
                index=idx,
                media_url=filename,
            )
            idx += 1
            saved.append(attachment)
        return saved
    except Exception as e:
        print(e.with_traceback(e.__traceback__))
        return None
