from sqlalchemy import Boolean, Column, Integer, String, Text, TIMESTAMP, JSON, func
from database.database import Base
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(30), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(255), nullable=True)
    email_verified_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

class Credentials(Base):
    __tablename__ = "credentials"

    credential_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # salt = Column(String(255), nullable=False)
    hash_algorithm = Column(String(50), nullable=False)

class Post(Base):
    __tablename__ = "posts"

    post_id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    vote = Column(Integer, default=0, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)

class Comment(Base):
    __tablename__ = "comments"

    comment_id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, nullable=False)
    author_id = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    vote = Column(Integer, default=0, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)

class Attachment(Base):
    __tablename__ = "attachments"

    attachment_id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, nullable=False)
    media_url = Column(String(255), nullable=False)
    media_type = Column(String(10), nullable=False)
    media_metadata = Column(JSON, nullable=True)
    index = Column(Integer, nullable=False)
    uploaded_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False, default=func.now() + func.interval('30 minutes'))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    token_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False, default=func.now() + func.interval('30 days'))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())