from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from routers import auth, users, posts, comments, tools
from os import getenv
from dotenv import load_dotenv

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    env = getenv("APP_ENV")
    if env != "test":
        from database import database
        print("Not in test env")
        # Drop all tables if this is dev env
        database.create_db_and_tables(env == "development")
        if env == "development":
            from database import testdata
            testdata.prepareForTest()
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(tools.router)