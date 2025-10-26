from datetime import datetime, timezone
from typing import Annotated
import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from database.database import Base, get_db, Db_dependency
from database.models import User, Post, Comment, Credentials
from database import models
from routers.dependencies import getUserFromToken, oauth2_scheme
from main import app

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


@pytest.fixture(scope="package")
def client(mock_db):
    def override_get_db():
        yield mock_db
    app.dependency_overrides[getUserFromToken] = getFakeUser
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client