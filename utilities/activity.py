from datetime import datetime, timezone
from typing import Literal
from database.database import Db_dependency
from database.models import Activity, Following, Notification, User
from database.outputmodel import OutputNotification
from configs.config_validation import Pattern
from utilities.user import getUserByUsername
import re

Action = Literal['comment', 'post', 'reply', 'votepost', 'votecomment']

async def logActivity(actor_id: int, db: Db_dependency, action: Action, content: str, action_id: int, target_noti_id: int = None):
    """
    Log user activities for traceback and generate notifications.

    Params:
        actor_id: ID of user issuing activity (creating post, comment, vote, ...)
        db: Database session object
        action: Type of action, using ActionType Enum in config_activity
        content: Content of action. Example: Post content, comment content, upvote, downvote,...
        action_id: ID of object created after the action: comment_id, post_id,...
        target_noti_id: ID of user whose object this action targets. For example, comment targets post, reply targets comment, follow target user,...
    
    Returns:
        None
    """
    
    act = Activity(
        actor_id = actor_id,
        action = action,
        action_id = action_id
    )
    new_act = True

    # Non-vote action: Post, comment
    if not action.startswith('vote') :
        mentionList = {user.user_id for user in await getMentionedUser(content, db)}
        for user_id in mentionList:
            if user_id == actor_id:
                continue
            act.notifications.append(createNotification(user_id, "mention"))
        
        if action == 'post':
            followers = db.query(Following).filter(Following.following_user_id == actor_id, Following.unfollow == False).all()
            for follower in followers:
                if follower.follower_id not in mentionList:
                    act.notifications.append(createNotification(follower.follower_id, "post"))
        elif actor_id != target_noti_id:
            act.notifications.append(createNotification(target_noti_id, action))
    
    # Vote action
    elif actor_id != target_noti_id:
        voteActivity =  db.query(Activity).filter(Activity.actor_id == actor_id, Activity.action == action, Activity.action_id == action_id).first()
        if voteActivity is not None:
            new_act = False
            now = datetime.now(timezone.utc)
            voteActivity.created_at = now
            if len(voteActivity.notifications) == 0:
                voteActivity.notifications.append(createNotification(target_noti_id, action))
            else:
                for noti in voteActivity.notifications:
                    noti.created_at = now
                    noti.is_read = False
                    noti.is_deleted = False
        else:
            act.notifications.append(createNotification(target_noti_id, action))

    if new_act:
        db.add(act)
    db.commit()

async def getMentionedUser(content: str, db: Db_dependency):
    username = re.findall(r"@" + Pattern.USERNAME_PATTERN, content)
    users = []
    for n in username:
        u = await getUserByUsername(n[1:], db)
        if u is not None:
            users.append(u)
    return users

def createNotification(user_id: int, action_type: str):
    noti = Notification(
        user_id=user_id,
        action_type=action_type,
    )
    return noti

async def getNotifications(user: User, db: Db_dependency, cursor: datetime):
    NOTI_PAGE_LIMIT = 10
    noti = db.query(Notification).filter(
        Notification.user_id == user.user_id,
        Notification.is_deleted == False,
        Notification.created_at < cursor,
    ).order_by(Notification.created_at.desc()).limit(NOTI_PAGE_LIMIT).all()
    
    output = []
    for n in noti:
        activity: Activity = n.activity
        actor = db.query(User).filter(User.user_id == activity.actor_id).first()
        
        output.append(OutputNotification(
            action_type=activity.action,
            action_id=activity.action_id,
            is_read=n.is_read,
            actor_username=actor.username,
            actor_avatar=actor.avatar_filename,
        ))
    return output