from database.database import Db_dependency
from database.models import Post, Attachment
from database.outputmodel import PostWithAttachments, SimpleAttachment

async def getPost(post_id: int, db: Db_dependency):
    return db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()

async def getOutputPost(post_id: int, db: Db_dependency):
    post = await getPost(post_id, db)

    if post is None:
        return None
    attachments = db.query(Attachment).filter(Attachment.post_id == post_id).order_by(Attachment.index.asc()).all()
    simple_attachments = [
        SimpleAttachment(
            media_type=a.media_type,
            media_url=a.media_url,
            # media_metadata=str(a.media_metadata),
            media_metadata=a.media_metadata,
            index=a.index
        ) for a in attachments
    ]
    output = PostWithAttachments(
        post_id=post.post_id,
        title=post.title,
        content=post.content,   
        vote=post.vote,
        comment_count=post.comment_count,
        created_at=post.created_at,
        is_modified=(post.updated_at > post.created_at),
        attachments=simple_attachments
    )
    return output