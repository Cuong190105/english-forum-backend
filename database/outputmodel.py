"""
This module contains Output Models.\n
Output models have modified properties from DB Models that provides enough information to send to client, hides unnecessary or confidential info.\n
The properties are created by adding or removing fields from original models, or merging some tables.\n
"""
from pydantic import BaseModel
from database.models import User
from datetime import datetime

class SimpleUser(BaseModel):
    username: str
    bio: str | None
    avatar_url: str | None

class SimpleAttachment(BaseModel):
    media_url: str
    media_type: str
    media_metadata: str
    index: int

class OutputPost(BaseModel):
    post_id: int
    title: str
    content: str
    vote: int
    user_vote: int
    comment_count: int
    created_at: datetime
    is_modified: bool
    attachments: list[SimpleAttachment] | None

class SimpleComment(BaseModel):
    author_id: int
    content: int
    vote: int
    created_at: datetime
    is_modified: bool

class OutputNotification(BaseModel):
    actor_id: int
    action_type: str
    action_id: int
    is_read: bool
    brief: str
