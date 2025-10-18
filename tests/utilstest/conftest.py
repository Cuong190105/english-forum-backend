import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.database import Base
from database.models import User, Post, Comment, Credentials
from datetime import datetime, timezone

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
        tag = "Tag 1"
    )
    post2 = Post(
        title = "Test 2",
        content = "Test content 2",
        tag = "Tag 2"
    )
    user1.posts.append(post1)
    user2.posts.append(post2)

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