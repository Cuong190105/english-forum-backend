from fastapi import FastAPI
from routers import auth, users, posts, comments, tools
from database import database

app = FastAPI()

database.create_db_and_tables()

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(tools.router)