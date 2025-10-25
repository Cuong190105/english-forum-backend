from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo
from fastapi import APIRouter, File, Form,  HTTPException, Query, UploadFile, status, Depends
from pydantic import EmailStr
from database.database import Db_dependency
from database.models import Following
from database.outputmodel import SimpleUser
from routers.dependencies import User_auth
from utilities import account, mailer, security, user as userutils, attachments, post, comment
from configs.config_auth import OTP_Purpose
from configs.config_user import Relationship
from configs.config_validation import Pattern
router = APIRouter()

@router.get("/user", status_code=status.HTTP_200_OK, response_model=SimpleUser)
async def get_current_user(this_user: User_auth):
    """
    Get current user info
    """
    return userutils.getSimpleUser(this_user, this_user)

@router.get("/user/{username}", status_code=status.HTTP_200_OK, response_model=SimpleUser)
async def get_user(this_user: User_auth, username: str, db: Db_dependency):
    """
    Get user info by username
    """
    requested_user = await userutils.getUserByUsername(username, db)
    if requested_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return userutils.getSimpleUser(this_user, requested_user)

@router.put("/user/bio", status_code=status.HTTP_200_OK)
async def update_bio(bio: Annotated[str, Form(min_length=1)], this_user: User_auth, db: Db_dependency):
    """
    Update user bio.
    """
    await account.updateBio(db, this_user, bio)
    return {
        "message": "Bio updated successfully"
    }

@router.put("/user/username", status_code=status.HTTP_200_OK)
async def update_username(username: Annotated[str, Form(pattern=Pattern.USERNAME_PATTERN)], this_user: User_auth, db: Db_dependency):
    """
    Update user username.
    """

    # Check if username is unique
    record = await userutils.getUserByUsername(username, db)
    if record is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    
    # Update username
    await account.updateUsername(db, this_user, username)

    return {
        "message": "Username updated successfully"
    }

@router.put("/user/email", status_code=status.HTTP_200_OK)
async def update_email_address(email: Annotated[EmailStr, Form()], this_user: User_auth, db: Db_dependency):
    """
    Update user email address
    """

    # Check if email is unique
    record = await userutils.getUserByUsername(email, db)
    if record is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    # Send OTP to new email address for verification
    otp = await security.generateOtp(this_user.username, OTP_Purpose.OTP_EMAIL_CHANGE, db)
    if otp is None:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too soon to request a new OTP")
    
    try:
        await mailer.sendOtpMail(otp.otp_code, this_user.username, email, mailer.EMAIL_CHANGE)
    except:
        await security.invalidateOtp(db, otp)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send email to address: " + email)
    
    # Create email change request
    await account.createEmailChangeRequest(db, otp, this_user, email)

    return {
        "message": "An OTP has been sent to the new address."
    }

@router.put("/user/password", status_code=status.HTTP_200_OK)
async def update_password(password: Annotated[str, Form(pattern=Pattern.PASSWORD_PATTERN)], new_password: Annotated[str, Form(pattern=Pattern.PASSWORD_PATTERN)], this_user: User_auth, db: Db_dependency):
    """
    Update user password.
    """

    # Check if old password is correct
    if not security.verifyPassword(password, this_user.credential.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Old password is incorrect")

    # Update password
    await account.updatePassword(db, this_user, new_password)

    return {
        "message": "Password updated."
    }

@router.get("/cancel/emailchange/{token}", status_code=status.HTTP_200_OK)
async def cancel_mail_update(token: str, db: Db_dependency):
    """
    Cancel email change request.
    """
    
    if not await security.cancelEmailChangeRequest(db, token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or Expired URL")
    
    return {
        "message": "Email change cancelled."
    }

@router.post("/user/email/confirm", status_code=status.HTTP_200_OK)
async def confirm_email_update(otp: Annotated[str, Form(pattern=Pattern.OTP_PATTERN)], this_user: User_auth, db: Db_dependency):
    """
    Confirm email change request and update new email address.
    """

    if not await account.updateEmail(db, this_user, otp):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP or email change request cancelled")

    return {
        "message": "Email updated successfully"
    }

@router.put("/user/avatar", status_code=status.HTTP_200_OK)
async def update_avatar(db: Db_dependency, this_user: User_auth, new_avatar: UploadFile):
    if not await attachments.validateFile(new_avatar):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid file. Avatar must have type jpg, png, or gif, and size less than 5MB.")
    this_user.avatar_filename = await attachments.saveFile(new_avatar, purpose='avatar')
    db.commit()
    return {
        "message": "Avatar updated successfully"
    }

@router.post("/user/{username}/{reltype}", status_code=status.HTTP_200_OK)
async def change_relationship(this_user: User_auth, username: str, reltype: Relationship, db: Db_dependency):
    """
    Change user's relationship with another user.
    Relationship can be: follow, unfollow (block and unblock added later)
    """
    if this_user.username == username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Self following not allowed")
    target = await userutils.getUserByUsername(username, db)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not await userutils.changeRelationship(db, this_user, target, reltype):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Something went wrong")
    return {
        "message": "Relationship changed"
    }

@router.get("/user/{username}/followers", status_code=status.HTTP_200_OK)
async def get_followers_list(this_user: User_auth, db: Db_dependency, username: str):
    """
    Get a list of user's followers
    """
    user = await userutils.getUserByUsername(username, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user.followers

@router.get("/user/{username}/following", status_code=status.HTTP_200_OK)
async def get_following_list(this_user: User_auth, db: Db_dependency, username: str):
    """
    Get a list of user's following.
    """
    user = await userutils.getUserByUsername(username, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user.following

@router.get("/user/{username}/posts", status_code=status.HTTP_200_OK)
async def get_user_posts(db: Db_dependency, this_user: User_auth, username: str, cursor: datetime | None= None):
    if cursor is None:
        cursor = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    user = await userutils.getUserByUsername(username, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return await post.getUserPosts(this_user, user, cursor)

@router.get("/user/{username}/comments", status_code=status.HTTP_200_OK)
async def get_user_posts(db: Db_dependency, this_user: User_auth, username: str, cursor: datetime | None= None):
    if cursor is None:
        cursor = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    user = await userutils.getUserByUsername(username, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return await comment.getUserComments(this_user, user, cursor)