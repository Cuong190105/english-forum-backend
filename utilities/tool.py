from database.database import Db_dependency
from database.models import User, Post

async def search(db: Db_dependency, keyword: str):
    """
    Search for users and posts that contain given keyword.

    Params:
        db: Database session object.
        keyword: Word or phrase in target search result

    Returns:
        dict: Contains a list of matching users and a list of matching posts
    """

    param = "%" + keyword + "%"
    users = db.query(User).filter(User.username.ilike(param)).all()
    posts = db.query(Post).filter(Post.content.ilike(param)).all()

    return {
        "users": users,
        "posts": posts,
    }