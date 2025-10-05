from fastapi import FastAPI
from routers import auth, users, posts, comments
from database import database
from middleware.verify import VerifyUserMiddleware

app = FastAPI()

database.create_db_and_tables()

# app.add_middleware(VerifyUserMiddleware)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)

# @app.post("/upload-post")
# def uploadPost(title: str, content: str, image: bytes | None = None):
#     # createPost()
#     pass

# @app.get("/")
# def getNewPosts():
#     pass

# @app.get("/posts/{post_Id}")
# def getPost(post_Id: int):
#     pass

# @app.get("/posts/{post_Id}/comments/{comment_Id}")
# def getComments():
#     pass

# @app.post("/posts/{post_Id}/comments")
# def addComment(post_Id: int, content: str):
#     # addCommentToPost()
#     pass

# @app.post("/posts/{post_Id}/vote")
# def votePost(post_Id: int, votetype: str):
#     # upvote()
#     pass

# @app.post("/posts/{post_Id}/unvote")
# def unvotePost(post_Id: int):
#     # removeUpvote()
#     pass

# @app.post("/posts/{post_Id}/comments/{comment_Id}/vote")
# def voteComment(post_Id: int, comment_Id: int, votetype: str):
#     # upvote()
#     pass

# @app.post("/posts/{post_Id}/comments/{comment_Id}/unvote")
# def unvoteComment(post_Id: int, comment_Id: int):
#     # removeUpvote()
#     pass

# @app.put("/posts/{post_Id}")
# def updatePost(post_Id: int, title: str | None, content: str | None, image: bytes | None = None):
#     # updatePostDetails()
#     pass

# @app.delete("/posts/{post_Id}")
# def deletePost(post_Id: int):
#     # deletePostById()
#     pass

# @app.put("/posts/{post_Id}/comments/{comment_Id}")
# def updateComment(post_Id: int, comment_Id: int, content: str):
#     # updateCommentDetails()
#     pass

# @app.delete("/posts/{post_Id}/comments/{comment_Id}")
# def deleteComment(post_Id: int, comment_Id: int):
#     # deleteCommentById()
#     pass

# @app.get("/search")
# def search(query: str):
#     # search()
#     pass

