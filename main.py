from fastapi import FastAPI, HTTPException, Request
from contextlib import asynccontextmanager

from routers import auth, users, posts, comments, tools
from os import getenv
from dotenv import load_dotenv
import traceback

load_dotenv()

env = getenv("APP_ENV")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if env != "test":
        from database import database
        print("Not in test env")
        # Drop all tables if this is dev env
        database.create_db_and_tables(env == "development")
        if env == "test":
            from database import testdata
            testdata.prepareForTest()
    yield

app = FastAPI(lifespan=lifespan, debug= env != 'production')

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(tools.router)

# @app.exception_handler(HTTPException)
# async def http_exception_handler(request: Request, exc:HTTPException):
#     print(traceback.print_tb(exc.__traceback__))
#     raise exc