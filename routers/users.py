from fastapi import APIRouter,  HTTPException, status, Depends
from pydantic import EmailStr
from database.database import Db_dependency
from database.models import Following
from database.outputmodel import SimpleUser
from routers.dependencies import User_auth
from utilities import account, mailer, security, user
from configs.config_auth import OTP_Purpose
from configs.config_user import Relationship
router = APIRouter()

@router.get("/users", status_code=status.HTTP_200_OK, response_model=SimpleUser)
async def get_current_user(this_user: User_auth):
    """
    Get current user info
    """
    return user.getSimpleUser(this_user)

@router.get("/user/{username}", status_code=status.HTTP_200_OK, response_model=SimpleUser)
async def get_user(this_user: User_auth, username: str, db: Db_dependency):
    """
    Get user info by username
    """
    return user.getSimpleUser(await account.getUserByUsername(username, db))

@router.put("/user/bio", status_code=status.HTTP_200_OK)
async def update_bio(bio: str, this_user: User_auth, db: Db_dependency):
    """
    Update user bio.
    """
    account.updateBio(db, this_user, bio)
    return {
        "message": "Bio updated successfully"
    }

@router.put("/user/username", status_code=status.HTTP_200_OK)
async def update_username(username: str, user: User_auth, db: Db_dependency):
    """
    Update user username.
    """

    # Check if username is unique
    record = await account.getUserByUsername(username)
    if record is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    
    # Update username
    account.updateUsername(db, user, username)

    return {
        "message": "Username updated successfully"
    }

@router.put("/user/email", status_code=status.HTTP_200_OK)
async def update_email_address(email: EmailStr, this_user: User_auth, db: Db_dependency):
    """
    Update user email address
    """

    # Check if email is unique
    record = account.getUserByUsername(email)
    if record is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    # Send OTP to new email address for verification
    otp = security.generateOtp(user.username, OTP_Purpose.OTP_EMAIL_CHANGE, db)
    await mailer.sendOtpMail(otp, user.username, email, mailer.PASSWORD_RESET)
    
    # Create email change request
    await account.createEmailChangeRequest(db, otp, this_user, email)

    return {
        "message": "An OTP has been sent to the new address."
    }

@router.delete("/cancel/emailchange/{token}", status_code=status.HTTP_200_OK)
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
async def confirm_email_update(otp: str, this_user: User_auth, db: Db_dependency):
    """
    Confirm email change request and update new email address.
    """

    if not await account.updateEmail(db, this_user, otp):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP or email change request cancelled")

    return {
        "message": "Email updated successfully"
    }

@router.post("/user/{username}/{reltype}", status_code=status.HTTP_200_OK)
async def change_relationship(this_user: User_auth, username: str, reltype: str, db: Db_dependency):
    """
    Change user's relationship with another user.
    Relationship can be: follow, unfollow (block and unblock added later)
    """
    target = await account.getUserByUsername(username)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not await user.changeRelationship(this_user, target, reltype):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Something went wrong")
    return {
        "message": "User followed"
    }