from configs.config_user import Relationship
from database.database import Db_dependency
from database.outputmodel import SimpleUser
from database.models import Comment, Post, User, Following, PostVote, CommentVote
from sqlalchemy import or_

async def getUserByUsername(username: str, db: Db_dependency):
    """
    Get user by username.

    Parameters:
        username: The username of user. Can be username or email.
        db: Database session object.

    Returns:
        Optional[models.User]: user if found, else None.
    """
    user = db.query(User).filter(or_(User.username == username, User.email == username)).first()
    return user

def getUpvoteCount(user: User):
    """
    Count all upvotes this user get on their posts and comments.

    Params:
        user: Target user

    Returns:
        int: Upvote count
    """

    voteCount = 0

    for p in user.posts:
        voteCount += p.votes.filter(PostVote.value == 1).count()
    for c in user.comments:
        voteCount += c.votes.filter(CommentVote.value == 1).count()
    return voteCount

def getSimpleUser(this_user: User, user: User):
    """
    Create `SimpleUser` object from `User` data for output.

    Params:
        this_user: Current session user.
        user: User object need simplified.

    Returns:
        SimpleUser: Output simple user data.
    """

    return SimpleUser(
        username=user.username,
        bio=user.bio,
        avatar_filename=user.avatar_filename,
        following=this_user.following.filter(User.user_id == user.user_id).first() is not None,
        follower_count=len(list(user.followers)),
        following_count=len(list(user.following)),
        post_count=len(list(user.posts.filter(Post.is_deleted == False))),
        comment_count=len(list(user.comments.filter(Comment.is_deleted == False))),
        upvote_count=getUpvoteCount(user),
    )

async def changeRelationship(db: Db_dependency, actor: User, target: User, reltype: Relationship):
    """
    Change relationship between 2 users.

    Params:
        actor: User creating the relation.
        target: User receiving the relation.
        reltype: Relation type. Takes value from `config_user.Relationship` enum.
    
    Returns:
        True if relation initialized, otherwise False.
    """

    # Early version: Only `follow` relationship. Later will update `block` relationship

    # Check if a relation already exists
    record = db.query(Following).filter(
        Following.follower_id == actor.user_id,
        Following.following_user_id == target.user_id
    ).first()

    if record is None:
        new_relation = Following(
            follower_id = actor.user_id,
            following_user_id=target.user_id,
            # reltype=reltype
            unfollow=reltype=='unfollow'
        )
        db.add(new_relation)
    else:
        # Simple logic for follow and unfollow
        print("record found")
        if reltype == 'unfollow':
            record.unfollow = True
        elif reltype == 'follow':
            record.unfollow = False
    db.commit()
    return True