from datetime import datetime, timezone
from typing import Literal
from database.database import Db_dependency
from database.models import Activity, Following, Notification, Comment
from configs.config_validation import Pattern
from utilities.user import getUserByUsername
import re

Action = Literal['comment', 'post', 'reply', 'votepost', 'votecomment']

async def logActivity(actor_id: int, db: Db_dependency, action: Action, content: str, action_id: int, target_noti_id: int = None):
    """
    Log user activities for traceback and generate notifications.
    :param actor_id: ID of user issuing activity (creating post, comment, vote, ...)
    :param action: Type of action, using ActionType Enum in config_activity
    :param action_id: ID of object created after the action: comment_id, post_id,...
    :param target_noti_id: ID of user whose object this action targets. For example, comment targets post, reply targets comment, follow target user,...
    """
    
    act = Activity(
        actor_id = actor_id,
        action = action,
        action_id = action_id
    )
    new_act = True
    if not action.startswith('vote') :
        mentionList = {user.user_id for user in await getMentionedUser(content, db)}
        for user_id in mentionList:
            act.notifications.append(createNotification(user_id, "mention"))
        
        if action == 'post':
            followers = db.query(Following).filter(Following.following_user_id == actor_id, Following.unfollow == False).all()
            for follower in followers:
                if follower.follower_id not in mentionList:
                    act.notifications.append(createNotification(follower.follower_id, "post"))
        else:
            act.notifications.append(createNotification(target_noti_id, action))
    else:
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