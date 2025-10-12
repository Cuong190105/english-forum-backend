import uuid
from sqlalchemy import Boolean, Column, Integer, String, Text, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import relationship
from database.database import Base
from configs.config_auth import Duration
from datetime import datetime, timezone, timedelta

class User(Base):
    __tablename__ = "users"

    # _________Fields_____________
    user_id = Column(Integer, primary_key=True)
    username = Column(String(30), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(255), nullable=True)
    email_verified_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    # _________Relationship_____________
    credential = relationship("Credentials", back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan", passive_deletes=True)
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan", passive_deletes=True)
    activities = relationship("Activity", back_populates="actor", cascade="all, delete-orphan", passive_deletes=True)
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    following = relationship(
        "User",
        secondary="following",
        primaryjoin=lambda: (User.user_id==Following.follower_id) & (Following.unfollow==False),
        secondaryjoin=lambda: User.user_id==Following.following_user_id,
        backref="followers"
    )
    postvotes = relationship("PostVote", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    commentvotes = relationship("CommentVote", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    


class Credentials(Base):
    __tablename__ = "credentials"

    # _________Fields_____________
    credential_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    password_hash = Column(String(255), nullable=False)
    hash_algorithm = Column(String(50), nullable=False)

    # _________Relationship_____________
    user = relationship("User", back_populates="credential", single_parent=True)

class Post(Base):
    __tablename__ = "posts"

    # _________Fields_____________
    post_id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    vote_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    tag = Column(Text, nullable=False)

    # _________Relationship_____________
    author = relationship("User", back_populates="posts", single_parent=True)
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan", passive_deletes=True)
    attachments = relationship("Attachment", back_populates="post", cascade="all, delete-orphan", passive_deletes=True)
    votes = relationship("PostVote", back_populates="post", cascade="all, delete-orphan", passive_deletes=True, lazy="dynamic")

class Comment(Base):
    __tablename__ = "comments"

    # _________Fields_____________
    comment_id = Column(Integer, primary_key=True)
    post_id = Column(ForeignKey("posts.post_id", ondelete="CASCADE"))
    author_id = Column(ForeignKey("users.user_id", ondelete="CASCADE"))
    reply_to_id = Column(ForeignKey("comments.comment_id", ondelete="CASCADE"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    vote_count = Column(Integer, default=0, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)

    # _________Relationship_____________
    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")
    reply_to = relationship("Comment", remote_side=[comment_id], back_populates="replies")
    replies = relationship("Comment", back_populates="reply_to", cascade="all, delete-orphan", passive_deletes=True, lazy="dynamic")
    votes = relationship("CommentVote", back_populates="comment", cascade="all, delete-orphan", passive_deletes=True, lazy="dynamic")

class Attachment(Base):
    __tablename__ = "attachments"

    # _________Fields_____________
    attachment_id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.post_id", ondelete="CASCADE"))
    media_url = Column(String(255), nullable=False)
    media_type = Column(String(10), nullable=False)
    media_metadata = Column(Text, nullable=True)
    index = Column(Integer, nullable=False)
    uploaded_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    is_deleted = Column(Boolean, default=False, nullable=False)

    # _________Relationship_____________
    post = relationship("Post", back_populates="attachments")

class OTP(Base):
    __tablename__ = "otps"

    # _________Fields_____________
    otp_id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False)
    otp_code = Column(String(6), nullable=False)
    jti = Column(String(36), index=True, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    expires_at = Column(TIMESTAMP, nullable=False, server_onupdate=None)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    purpose = Column(String(50), nullable=False)
    trials = Column(Integer, default=5, nullable=False)
    is_token_used = Column(Boolean, default=False, nullable=False)

    # _________Relationship_____________

class EmailChangeRequest(Base):
    __tablename__ = "email_change_tokens"

    # _________Fields_____________
    id = Column(Integer, primary_key=True)
    jti = Column(String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, nullable=False)
    new_email = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    is_revoked = Column(Boolean, nullable=False, default=False)

    # _________Relationship_____________

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    # _________Fields_____________
    token_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    jti = Column(String(36), index=True, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    expires_at = Column(TIMESTAMP, nullable=False, default=datetime.now(timezone.utc) + timedelta(days=Duration.REFRESH_TOKEN_EXPIRE_DAYS))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    is_revoked = Column(Boolean, default=False, nullable=False)

    # _________Relationship_____________

class Activity(Base):
    __tablename__ = "activities"

    # _________Fields_____________
    activity_id = Column(Integer, primary_key=True)
    actor_id = Column(ForeignKey("users.user_id", ondelete="CASCADE"))
    action = Column(Text, nullable=False)
    action_id = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # _________Relationship_____________
    actor = relationship("User", back_populates="activities", single_parent=True)
    notifications = relationship("Notification", back_populates="activity", cascade="all, delete-orphan", passive_deletes=True)

class Notification(Base):
    __tablename__ = "notifications"

    # _________Fields_____________
    noti_id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey("users.user_id", ondelete="CASCADE"))
    activity_id = Column(ForeignKey("activities.activity_id", ondelete="CASCADE"))
    action_type = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # _________Relationship_____________
    user = relationship("User", back_populates="notifications", single_parent=True)
    activity = relationship("Activity", back_populates="notifications", single_parent=True)
    
class Following(Base):
    __tablename__ = "following"

    # _________Fields_____________
    rel_id = Column(Integer, primary_key=True)
    follower_id = Column(ForeignKey("users.user_id", ondelete="CASCADE"))
    following_user_id = Column(ForeignKey("users.user_id", ondelete="CASCADE"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    unfollow = Column(Boolean, nullable=False, default=False)

class PostVote(Base):
    __tablename__ = "post_votes"

    # _________Fields_____________
    vote_id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey("users.user_id", ondelete="CASCADE"))
    post_id = Column(ForeignKey("posts.post_id", ondelete="CASCADE"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    value = Column(Integer, nullable=False, default=0)
    
    # _________Relationship_____________
    user = relationship("User", back_populates="postvotes", single_parent=True)
    post = relationship("Post", back_populates="votes", single_parent=True)

class CommentVote(Base):
    __tablename__ = "comment_votes"

    # _________Fields_____________
    vote_id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey("users.user_id", ondelete="CASCADE"))
    comment_id = Column(ForeignKey("comments.comment_id", ondelete="CASCADE"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    value = Column(Integer, nullable=False, default=False)
    
    # _________Relationship_____________
    user = relationship("User", back_populates="commentvotes", single_parent=True)
    comment = relationship("Comment", back_populates="votes", single_parent=True)