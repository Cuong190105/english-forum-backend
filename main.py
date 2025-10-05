from fastapi import FastAPI
from routers import auth, users
from routers import ai
from database import database
# from pydantic import BaseModel
app = FastAPI()
database.create_db_and_tables()
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(ai.router)
# class Attachment(BaseModel):
#     mediaId: int
#     mediaUrl: str
#     mediaType: str
#     metadata: dict | None
#     index: int
#     content: bytes

# class Post(BaseModel):
#     postId: int
#     authorId: int
#     title: str
#     content: str
#     attachments: list[Attachment] | None
#     vote: int

# class Comment(BaseModel):
#     commentId: int
#     postId: int
#     authorId: int
#     content: str
#     vote: int

# class User(BaseModel):
#     userId: int
#     username: str
#     email: str
#     profilePicture: Attachment | None
#     bio: str | None



# @app.get("/users")
# def getUser(user_Id: int):
#     return 

# @app.get("/users/{user_Id}")
# def getUser(user_Id: int):
#     return 

# @app.post("/login")
# def login(username: str, password: str):
#     # checkLogin(username, password)
#     pass

# @app.post("/register")
# def register(username: str, password: str, email: str):
#     # checkRegister()
#     # createUser()
#     # Login()
#     pass

# @app.post("/password-reset")
# def passwordReset(email: str):
#     # sendResetEmail()
#     pass

# @app.post("/password-change")
# def passwordChange(old_password: str | None, new_password: str, reset_token: str | None):
#     # verifyOldPassword()
#     # verifyResetToken()
#     # updatePassword()
#     pass

# @app.post("/logout")
# def logout():
#     # logoutUser()
#     pass

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

