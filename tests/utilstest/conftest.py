import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.database import Base
from database.models import User, Post, Comment, Credentials
from datetime import datetime, timedelta, timezone

@pytest.fixture(scope="package", autouse=True)
def connection(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("data") / "unit_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    yield engine
    engine.dispose()

@pytest.fixture(scope="class", autouse=True)
def setup_database(connection):
    Base.metadata.create_all(bind=connection)
    yield
    Base.metadata.drop_all(bind=connection)

@pytest.fixture(scope="package", autouse=True)
def mock_db(connection):
    # Setup database
    SessionLocal = sessionmaker(bind=connection)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="class")
def seed_data(mock_db):
# Create users
    user1 = User(
        username="username1",
        email="username1@example.com",
        email_verified_at=datetime.now(timezone.utc),
    )
    creds1 = Credentials(
        password_hash="$2b$12$pmpN3J/zSxS6L3EwetcT1enO7uxRrfe6zIcVvr8ZfgK2pxT0FbYly",
        hash_algorithm="bcrypt"
    )
    user1.credential = creds1

    user2 = User(
        username="username2",
        email="username2@example.com",
    )
    creds2 = Credentials(
        password_hash="$2b$12$TKdVCOcS4n3lQ4KlOkV2ZefyNmPKkFq0.Jxn2e7.QmmF.mmO8ID3K",
        hash_algorithm="bcrypt"
    )
    user2.credential = creds2

    # Create posts
    post1 = Post(
        title = "Test 1",
        content = "Test content 1",
        tag = "question",
        vote_count = 10,
        comment_count = 10,
        created_at = datetime.now(timezone.utc) - timedelta(minutes=32),
    )
    post2 = Post(
        title = "Test 2",
        content = "Test content 2",
        tag = "discussion",
        vote_count = 15,
        comment_count = 2,
        created_at = datetime.now(timezone.utc) - timedelta(hours=1, minutes=7),
    )
    post3 = Post(
        title = "Test 3",
        content = "Test content 3",
        tag = "question",
        vote_count = -3,
        comment_count = 34,
        created_at = datetime.now(timezone.utc) - timedelta(hours=5, minutes=23),
    )
    post4 = Post(
        title = "Test 4",
        content = "Test content 4",
        tag = "discussion",
        vote_count = 25,
        comment_count = 0,
        created_at = datetime.now(timezone.utc) - timedelta(hours=7),
    )
    post5 = Post(
        title = "Test post 5",
        content = "Test content post 5",
        tag = "discussion",
        vote_count = 100,
        comment_count = 120,
        created_at = datetime.now(timezone.utc) - timedelta(days=1, hours=5, minutes=2),
    )
    post6 = Post(
        title = "Test 6",
        content = "Test content 6",
        tag = "question",
        vote_count = 10,
        comment_count = 120,
        created_at = datetime.now(timezone.utc) - timedelta(hours=17, minutes=24),
    )
    post7 = Post(
        title = "Test 7",
        content = "Test content 7",
        tag = "question",
        vote_count = 10,
        comment_count = 10,
        created_at = datetime.now(timezone.utc) - timedelta(hours=1),
    )
    post8 = Post(
        title = "Test 8",
        content = "Test content 8",
        tag = "discussion",
        vote_count = 128,
        comment_count = 101,
        created_at = datetime.now(timezone.utc) - timedelta(days=8, hours=13, minutes=58),
    )
    post9 = Post(
        title = "Test 9",
        content = "Test content 9",
        tag = "discussion",
        vote_count = 225,
        comment_count = 171,
        created_at = datetime.now(timezone.utc) - timedelta(days=35, hours=5, minutes=38),
    )
    post10 = Post(
        title = "Test 10",
        content = "Test content 10",
        tag = "discussion",
        vote_count = 422,
        comment_count = 275,
        created_at = datetime.now(timezone.utc) - timedelta(days=104, hours=8, minutes=29),
    )
    user1.posts.append(post1)
    user2.posts.append(post2)
    user1.posts.append(post3)
    user2.posts.append(post4)
    user1.posts.append(post5)
    user2.posts.append(post6)
    user1.posts.append(post7)
    user2.posts.append(post8)
    user1.posts.append(post9)
    user2.posts.append(post10)

    # Create comments
    cmt1 = Comment(
        content = "Test comment 1",
    )
    cmt2 = Comment(
        content = "Test comment 2",
    )
    cmt3 = Comment(
        content = "Test comment 3",
    )
    user1.comments.append(cmt1)
    user2.comments.append(cmt2)
    user1.comments.append(cmt3)

    post1.comments.append(cmt1)
    post1.comments.append(cmt2)
    post2.comments.append(cmt3)

    mock_db.add(user1)
    mock_db.add(user2)
    mock_db.commit()