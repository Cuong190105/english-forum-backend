from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utilities import post, user as userutils, comment
from database.database import Base
from database.models import User, Post, Comment
from datetime import datetime, timedelta, timezone

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestPostComment:
    
    @pytest.mark.asyncio
    async def test_getPost(self, mock_db):
        assert await post.getPost(1, mock_db) is not None
        assert await post.getPost(2, mock_db) is not None
        assert await post.getPost(999, mock_db) is None

    @pytest.mark.asyncio
    async def test_feedQuery(self, mock_db):
        posts = await post.queryFeed(mock_db, cursor=datetime.now(timezone.utc), criteria='latest', limit=15)
        assert len(posts) == 10
        assert len(await post.queryFeed(mock_db, cursor=datetime.now(timezone.utc), criteria='discussion', limit=15)) == 6
        assert len(await post.queryFeed(mock_db, cursor=datetime.now(timezone.utc), criteria='question',limit=3)) == 3
        assert len(await post.queryFeed(mock_db, cursor=datetime.now(timezone.utc) - timedelta(days=1), criteria='latest', limit=15)) == 4
        assert await post.queryFeed(mock_db, cursor=datetime.now(timezone.utc), criteria='trending', limit=15) != posts
        assert await post.queryFeed(mock_db, cursor=datetime.now(timezone.utc), criteria='treng', limit=15) is None
        assert await post.queryFeed(mock_db, cursor=datetime.now(timezone.utc), criteria='trending', limit=-1) is None

    @pytest.mark.asyncio
    async def test_createPost(self, mock_db):
        user = await userutils.getUserByUsername("username1", mock_db)
        new_post = await post.createPost(mock_db, user, "New Post", "New Content", "question")
        assert new_post.post_id is not None
        assert new_post.title == "New Post"

        fetched_post = mock_db.query(Post).filter(Post.post_id == 11).first()
        assert fetched_post is not None
        assert fetched_post.title == "New Post"
    
    @pytest.mark.asyncio
    async def test_updatePost(self, mock_db):
        post1 = mock_db.query(Post).filter(Post.post_id == 1).first()
        await post.updatePost(mock_db, post1, "Update Title", "Update content", "Tag 1")

        assert post1.title == "Update Title"
        assert mock_db.query(Post).filter(Post.post_id == 1).first().content == "Update content"
    
    @pytest.mark.asyncio
    async def test_deletePost(self, mock_db):
        post3 = mock_db.query(Post).filter(Post.post_id == 3).first()
        await post.deletePost(mock_db, post3)

        assert mock_db.query(Post).filter(Post.post_id == 3, Post.is_deleted == False).first() is None
        assert await post.getPost(3, mock_db) is None

    @pytest.mark.asyncio
    async def test_votePost(self, mock_db):
        user1 = mock_db.query(User).filter(User.username == "username1").first()
        user2 = mock_db.query(User).filter(User.username == "username2").first()
        post11 = mock_db.query(Post).filter(Post.post_id == 11).first()

        # Upvote
        await post.votePost(mock_db, user1, post11, 1)
        assert post11.vote_count == 1
        await post.votePost(mock_db, user2, post11, 1)
        assert post11.vote_count == 2

        # Change to downvote
        await post.votePost(mock_db, user1, post11, -1)
        assert post11.vote_count == 0
        await post.votePost(mock_db, user1, post11, -1)
        assert post11.vote_count == 0

        # Remove vote
        await post.votePost(mock_db, user1, post11, 0)
        assert post11.vote_count == 1

        # Invalid vote value
        result = await post.votePost(mock_db, user1, post11, 2)
        assert result is False
        assert post11.vote_count == 1

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestComment:

    @pytest.mark.asyncio
    async def test_getComments(self, mock_db):
        user1 = mock_db.query(User).filter(User.username == "username1").first()
        post1 = mock_db.query(Post).filter(Post.post_id == 1).first()
        post2 = mock_db.query(Post).filter(Post.post_id == 2).first()
        assert len(await comment.getComments(mock_db, post1, user1, 0, 10)) == 2
        assert len(await comment.getComments(mock_db, post2, user1, 0, 10)) == 1

    @pytest.mark.asyncio
    async def test_createComment(self, mock_db):
        user1 = mock_db.query(User).filter(User.username == "username1").first()
        user2 = mock_db.query(User).filter(User.username == "username2").first()
        post1 = mock_db.query(Post).filter(Post.post_id == 1).first()

        # Test normal comment
        await comment.createComment(mock_db, user1, post1, "New Comment 4", None)
        assert mock_db.query(Comment).filter(Comment.comment_id == 4).first() is not None

        # Test reply
        reply1 = await comment.createComment(mock_db, user2, post1, "New Comment 5", 1)
        assert mock_db.query(Comment).filter(Comment.comment_id == 5).first().reply_to_id == 1
        assert reply1.reply_to.comment_id == 1

    @pytest.mark.asyncio
    async def test_updateComment(self, mock_db):
        cmt1 = mock_db.query(Comment).filter(Comment.comment_id == 1).first()

        # Test output result
        assert await comment.updateComment(mock_db, cmt1, "Update comment 1") is True
        assert await comment.updateComment(mock_db, cmt1, "") is False

        # Test database update
        assert mock_db.query(Comment).filter(Comment.comment_id == 1).first().content == "Update comment 1"

    @pytest.mark.asyncio
    async def test_deleteComment(self, mock_db):
        
        cmt1 = mock_db.query(Comment).filter(Comment.comment_id == 1).first()
        assert await comment.deleteComment(mock_db, cmt1) is True
        assert await comment.getCommentById(mock_db, 1) is None

    @pytest.mark.asyncio
    async def test_voteComment(self, mock_db):
        user1 = mock_db.query(User).filter(User.username == "username1").first()
        user2 = mock_db.query(User).filter(User.username == "username2").first()
        cmt1 = mock_db.query(Comment).filter(Comment.post_id == 1).first()

        # Upvote
        await comment.voteComment(mock_db, user1, cmt1, 1)
        assert cmt1.vote_count == 1
        await comment.voteComment(mock_db, user2, cmt1, 1)
        assert cmt1.vote_count == 2

        # Change to downvote
        await comment.voteComment(mock_db, user1, cmt1, -1)
        assert cmt1.vote_count == 0
        await comment.voteComment(mock_db, user1, cmt1, -1)
        assert cmt1.vote_count == 0

        # Remove vote
        await comment.voteComment(mock_db, user1, cmt1, 0)
        assert cmt1.vote_count == 1

        # Invalid vote value
        result = await comment.voteComment(mock_db, user1, cmt1, 2)
        assert result is False
        assert cmt1.vote_count == 1