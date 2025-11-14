from datetime import datetime, timezone
from io import BytesIO
from typing import Annotated
import bcrypt
from fastapi import Depends, HTTPException, Request, UploadFile, status
from fastapi.testclient import TestClient
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from database.database import Base, get_db, Db_dependency
from database.models import Activity, Notification, User, Post, Comment, Credentials, Following
from database import models
from routers.dependencies import getUserFromToken, oauth2_scheme
from main import app
from dotenv import load_dotenv
import os
load_dotenv()

REDIS_CONNECTIONSTRING = os.getenv("REDIS_CONNECTIONSTRING")

@pytest.fixture(scope="package")
def connection(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("data") / "api_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    yield engine
    engine.dispose()

@pytest.fixture(scope="class", autouse=True)
def setup_database(connection):
    Base.metadata.create_all(bind=connection)
    yield
    Base.metadata.drop_all(bind=connection)

@pytest.fixture(scope='function')
def check():
    print("Overridden:", app.dependency_overrides)
    # print("Engine URL:", engine.url)
    # print("Tables in DB:", inspect(engine).get_table_names())


@pytest.fixture(scope="function")
def mock_file():
    list_files = {
        "normal_jpg": (
            "virus.jpg",
            BytesIO(b"fake jpg content"),
            "image/jpg"
        ),
        "normal_jpeg": (
            "virus.jpeg",
            BytesIO(b"fake jpeg content"),
            "image/jpeg"
        ),
        "too_big_png": (
            "image.png",
            BytesIO(b"x" * (6 * 1024 * 1024)),
            "image/png"
        ),
        "normal_mp4": (
            "video.mp4",
            BytesIO(b"x" * (19 * 1024 * 1024)),
            "video/mp4"
        ),
        "too_big_mp4": (
            "fatvideo.mp4",
            BytesIO(b"x" * (101 * 1024 * 1024)),
            "video/mp4"
        ),
        "wrong_type_txt": (
            "document.txt",
            BytesIO(b"fake txt content"),
            "text/plain"
        ),
        "file7": (
            "virus1.jpeg",
            BytesIO(b"fake jpeg content"),
            "image/jpeg"
        ),
        "file8": (
            "virus2.jpeg",
            BytesIO(b"fake jpeg content"),
            "image/jpeg"
        ),
        "file9": (
            "virus3.jpeg",
            BytesIO(b"fake jpeg content"),
            "image/jpeg"
        ),
        "file10": (
            "virus4.jpeg",
            BytesIO(b"fake jpeg content"),
            "image/jpeg"
        ),
        "file11": (
            "virus5.jpeg",
            BytesIO(b"fake jpeg content"),
            "image/jpeg"
        ),
    }
    return list_files

@pytest.fixture(scope="class")
def seed_data(mock_db):
    # Create users
    mock_db.add(User(
        username="testuser1",
        email="email1@example.com",
        email_verified_at=datetime.now(timezone.utc),
    ))
    mock_db.add(User(
        username="testuser2",
        email="email2@example.com",
        email_verified_at=datetime.now(timezone.utc),
    ))
    mock_db.add(User(
        username="companion",
        email="emailcompanion@example.com",
        email_verified_at=datetime.now(timezone.utc),
    ))
    mock_db.add(Following(
        follower_id=3,
        following_user_id=1,
    ))

    password1 = bcrypt.hashpw("testuser1password".encode('utf-8'), bcrypt.gensalt())
    password2 = bcrypt.hashpw("testuser2password".encode('utf-8'), bcrypt.gensalt())

    mock_db.add(Credentials(
        user_id=1,
        password_hash=password1.decode('utf-8'),
        hash_algorithm="bcrypt"
    ))
    mock_db.add(Credentials(
        user_id=2,
        password_hash=password2.decode('utf-8'),
        hash_algorithm="bcrypt"
    ))

    mock_db.add(Post(
        author_id=1, 
        title="title1",
        content="content1",
        tag="tag1",
    ))
    mock_db.add(Post(
        author_id=2, 
        title="title2",
        content="content2",
        tag="tag2",
    ))
    mock_db.add(Comment(
        author_id=1,
        post_id=1, 
        content="content1",
    ))
    mock_db.add(Comment(
        author_id=2,
        post_id=1, 
        content="content2",
    ))
    mock_db.add(Activity(
        actor_id = 1,
        target_type = "comment",
        target_id = 1,
        action_type = "like",
        action_id = 1,
        created_at = datetime.now(timezone.utc),
    ))
    mock_db.add(Notification(
        user_id=1,
        activity_id=1,
        action_type="like",
    ))
    mock_db.commit()

async def getFakeUser(token: Annotated[str, Depends(oauth2_scheme)], db: Db_dependency, request: Request):
    user = db.query(User).filter(User.user_id == int(token)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized")
    
    path = request.scope.get("route").path
    if user.email_verified_at is None and not path.startswith("/register/"):
        print(path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You have to verify your email before using the app")
    return user

@pytest.fixture(scope="package")
def mock_db(connection):
    SessionLocal = sessionmaker(bind=connection)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest_asyncio.fixture(scope="function")
async def redis_client():
    client = await aioredis.from_url(REDIS_CONNECTIONSTRING, decode_responses=True)
    yield client
    await client.aclose()

@pytest_asyncio.fixture(scope="package")
async def async_client(mock_db):
    def override_get_db():
        yield mock_db
    app.dependency_overrides[getUserFromToken] = getFakeUser
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
