"""
This module contains Output Models.\n
Output models have modified properties from DB Models that provides enough information to send to client, hides unnecessary or confidential info.\n
The properties are created by adding or removing fields from original models, or merging some tables.\n
"""
from pydantic import BaseModel
from typing import Any, List, Optional
from database.models import User
from datetime import datetime

class SimpleUser(BaseModel):
    username: str
    bio: str | None
    avatar_filename: str | None
    following: bool
    follower_count: int
    following_count: int
    post_count: int
    comment_count: int
    upvote_count: int

class SimpleAttachment(BaseModel):
    media_filename: str
    media_type: str
    media_metadata: str
    index: int

class OutputPost(BaseModel):
    post_id: int
    author_username: str
    author_avatar: str | None
    title: str
    content: str
    tag: str
    vote_count: int
    user_vote: int
    comment_count: int
    created_at: datetime
    is_modified: bool
    attachments: list[SimpleAttachment] | None

class OutputComment(BaseModel):
    comment_id: int
    post_id: int
    reply_to_id: int | None
    author_username: str
    author_avatar: str | None
    content: str
    vote_count: int
    user_vote: int
    created_at: datetime
    is_modified: bool

class OutputNotification(BaseModel):
    actor_username: str
    actor_avatar: str | None
    action_type: str
    action_id: int
    target_type: str
    target_id: int
    is_read: bool


# =========================
# AI Generation Output Models
# =========================

class OutputAIGeneratedItems(BaseModel):
    """Response for /ai/generate endpoint: items only."""
    items: List[Any] = []


class OutputAIGeneratedWithTopic(BaseModel):
    """Response for /ai/generate-from-text endpoint: topic + items."""
    topic: str
    items: List[Any] = []
