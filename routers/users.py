from datetime import timedelta
from fastapi import APIRouter,  HTTPException, status, Depends
from pydantic import EmailStr
from database.database import Db_dependency
from database.models import User, EmailChangeRequest
from database.outputmodel import SimpleUser
from typing import Annotated
from sqlalchemy import func
from utilities import account, mailer
from configs.config_auth import Encryption, OTP_Purpose
router = APIRouter()

@router.get("/users", status_code=status.HTTP_200_OK, response_model=SimpleUser)
async def get_current_user(this_user: account.User_auth):
    """
    Get current user info
    """
    return SimpleUser(this_user)

@router.get("/user/{username}", status_code=status.HTTP_200_OK, response_model=SimpleUser)
async def get_user(this_user: account.User_auth, username: str):
    """
    Get user info by username
    """
    return await SimpleUser(account.getUserByUsername(username))

@router.put("/user/bio", status_code=status.HTTP_200_OK)
async def update_bio(bio: str, user: account.User_auth, db: Db_dependency):
    """
    Update user bio.
    """
    user.bio = bio
    user.updated_at = func.now()
    db.commit()
    return {
        "message": "Bio updated successfully"
    }

@router.put("/user/username", status_code=status.HTTP_200_OK)
async def update_username(username: str, user: account.User_auth, db: Db_dependency):
    """
    Update user username.
    """

    # Check if username is unique
    record = account.getUserByUsername(username)
    if record is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    
    # Update username
    user.username = username
    user.updated_at = func.now()
    db.commit()
    return {
        "message": "Username updated successfully"
    }

@router.put("/user/email", status_code=status.HTTP_200_OK)
async def update_email_address(email: EmailStr, user: account.User_auth, db: Db_dependency):
    """
    Update user email address
    """

    # Check if email is unique
    record = account.getUserByUsername(email)
    if record is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    
    # Send OTP to new email address for verification
    otp = account.otpGenerator(user.username, OTP_Purpose.OTP_EMAIL_CHANGE)
    await mailer.sendOtpMail(otp, user.username, email, mailer.PASSWORD_RESET)
    jwt = account.createToken(
        data={
            "jti": otp.jti,
            "user_id": user.user_id,
        },
        expires_delta=timedelta(days=365),
        secret_key=Encryption.SECRET_RESET_KEY
    )
    cancel_link = "myapp.com/cancel/emailchange/" + jwt
    await mailer.sendWarningChangingEmailMail(username=user.username, new_email=email, target_address=user.email, cancel_link=cancel_link)

    # Add email change token to DB. New email will be updated only after user verify.
    request = EmailChangeRequest(
        user_id=user.user_id,
        new_email=email,
        jti=otp.jti
    )

    db.add(request)
    db.commit()

    return {
        "message": "An OTP has been sent to the new address."
    }

@router.delete("/cancel/emailchange/{token}", status_code=status.HTTP_200_OK)
async def cancel_mail_update(token: str, db: Db_dependency):
    """
    Cancel email change request.
    """
    payload = account.validateToken(token, Encryption.SECRET_RESET_KEY)
    request = db.query(EmailChangeRequest).filter(EmailChangeRequest.jti == payload.get("jti")).first()
    if request is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL expired")
    
    request.is_revoked = True
    db.commit()
    return {
        "message": "Email change cancelled."
    }

@router.post("/user/email/confirm", status_code=status.HTTP_200_OK)
async def confirm_email_update(otp: str, user: account.User_auth, db: Db_dependency):
    """
    Confirm email change request and update new email address.
    """
    
    # Validate OTP and get jti
    record = account.validateOtp(otp)
    
    # Get email change request stored on DB before
    request = db.query(EmailChangeRequest).filter(EmailChangeRequest.jti == record.jti, EmailChangeRequest.user_id == user.user_id).first()
    user.email = request.new_email
    user.email_verified_at = func.now()
    user.updated_at = func.now()
    db.commit()

    return {
        "message": "Email updated successfully"
    }