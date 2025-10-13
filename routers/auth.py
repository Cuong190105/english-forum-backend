from configs.config_auth import *
from configs.config_validation import USERNAME_PATTERN
from database.database import Db_dependency
from database import models
from datetime import timedelta
from fastapi import APIRouter, HTTPException, status, Depends, Form, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import Annotated
from utilities import account, mailer, security
from routers.dependencies import User_auth, oauth2_scheme

class RegisterRequest(BaseModel):
    username: Annotated[str, Query(pattern=USERNAME_PATTERN)]
    password: Annotated[str, Query(min_length=8, max_length=255)]
    email: EmailStr

router = APIRouter()

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(request: Annotated[OAuth2PasswordRequestForm, Depends()], db: Db_dependency):
    """
    Handle login requests.

    Params:
        request: Register form with 2 fields: username and password. Email can be used as username
        db: Database session object.
    
    Returns:
        On success, return access token.\n
        On failure, return status code with detail.
    """
    
    user = await account.getUserByUsername(request.username, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Username not found")

    if not await security.verifyPassword(db, user, request.password):
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Incorrect password")
        
    # Create and return access and refresh token
    # Token-per-device login, each device is assigned a UUID for management. 
    
    refresh_token = await security.createRefreshToken(db, user)
    access_token = await security.createAccessToken(db, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: Annotated[RegisterRequest, Form()], db: Db_dependency):
    """
    Handle user registration requests.

    Params:
        request: Register form with 3 fields: username, password and email.
        db: Database session object.
    
    Returns:
        On success, return access token for automatic login. A verification mail will be sent.\n
        On failure, return status code with detail.
    """

    # Check if username or email already exists
    user = await account.getUserByUsername(request.username, db)
    if user is None:
        await account.getUserByUsername(request.email, db)
    if user is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already exists")
    
    # Create new user
    new_user = await account.createNewAccount(db, request.username, request.password, request.email)

    # Send account verification OTP
    otp = security.generateOtp(new_user.username, OTP_Purpose.OTP_REGISTER, db)
    await mailer.sendOtpMail(otp.otp_code, new_user.username, new_user.email, mailer.REGISTER)
    
    # Automatically log in the user after registration
    login_tokens = await login(OAuth2PasswordRequestForm(username=request.username, password=request.password, scope=""), db)

    return login_tokens

@router.post("/register/verify", status_code=status.HTTP_200_OK)
async def verify_account(this_user: User_auth, otp: str, db: Db_dependency):
    """
    Verify email address of newly created account.
    """

    # If this user's email address is verified, tell user to not verify again
    if this_user.email_verified_at != None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email verified before")

    # Verify OTP
    if not await account.verifyEmail(this_user, otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")
    
    return {
        "message": "Email has been verified successfully."
    }

@router.post("/register/resend", status_code=status.HTTP_200_OK)
async def resend_verification_email(this_user: User_auth, db: Db_dependency):
    """
    Send a new verification email.
    """
    
    # If this user's email address is verified, tell user to not verify again
    if this_user.email_verified_at != None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email verified before")
    
    otp = security.generateOtp(this_user.username, OTP_Purpose.OTP_REGISTER, db)
    await mailer.sendOtpMail(otp.otp_code, this_user.username, this_user.email, mailer.REGISTER)

    return {
        "message": "Verification email resent"
    }

@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_access_token(rf_token: str, db: Db_dependency):
    """
    Get a new access token.
    """
    access_token = await security.createAccessToken(db, rf_token)

    if access_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return {
        "message": "Token refreshed",
        "access_token": access_token
    }

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(token: Annotated[str, Depends(oauth2_scheme)], db: Db_dependency):
    """Handle user logout by invalidating tokens."""

    if not await security.invalidateRefreshToken(db, token):
        raise(HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token"))

    return {"message": "Logout successful"}
    
@router.post("/recover", status_code=status.HTTP_200_OK)
async def recover_password(username: str, db: Db_dependency):
    """
    Handle password recovery requests.\n
    If the username or email exists, send a recovery email.
    """
    
    # Check if user exists by username or email and then get user ID
    user = await account.getUserByUsername(username, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    otp = security.generateOtp(user.username, OTP_Purpose.OTP_PASSWORD_RESET, db)

    # Send recovery email
    await mailer.sendOtpMail(otp, user.username, user.email, mailer.PASSWORD_RESET)

    return {"message": "Recovery email sent"}

@router.post("/recover/verify")
async def verify_recovery_code(otp: str, username: str, db: Db_dependency):
    record = security.validateOtp(otp, username, OTP_Purpose.OTP_PASSWORD_RESET, db)
    reset_token = security.createToken(
        data={"sub": record.username, "jti": record.jti},
        expires_delta=timedelta(minutes=Duration.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        secret_key=Encryption.SECRET_RESET_KEY
    )

    return {
        "message": "OTP verified",
        "reset_token": reset_token
    }

@router.post("/reset")
async def reset_password(token: str, new_password: str, db: Db_dependency):
    """
    Reset user password.
    """
    
    if not await account.resetPassword(db, token, new_password):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

    return {"message": "Password reset successful"}