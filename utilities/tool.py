from database.database import Db_dependency
from database.models import User, Post
from utilities.user import getSimpleUser
from utilities.post import getOutputPost

async def search(db: Db_dependency, user: User, keyword: str):
    """
    Search for users and posts that contain given keyword.

    Params:
        db: Database session object.
        user: Current session user.
        keyword: Word or phrase in target search result

    Returns:
        dict: Contains a list of matching users and a list of matching posts
    """

    param = "%" + keyword + "%"

    users = db.query(User).filter(User.username.ilike(param)).all()
    posts = db.query(Post).filter(Post.content.ilike(param)).all()

    outputUsers = [await getSimpleUser(user, u) for u in users]
    outputPosts = [await getOutputPost(user, p) for p in posts]

    return {
        "users": outputUsers,
        "posts": outputPosts,
    }