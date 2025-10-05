from random import random
import uuid
from fastapi import APIRouter, HTTPException, status, Depends, Form, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from database.database import Db_dependency
from database import models
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Annotated
from utilities import account, mailer
from configs.config_auth import *

class RegisterRequest(BaseModel):
    username: Annotated[str, Query(min_length=8, max_length=50)]
    password: Annotated[str, Query(min_length=8, max_length=255)]
    email: EmailStr

router = APIRouter()

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(request: Annotated[OAuth2PasswordRequestForm, Depends()], db: Db_dependency):
    """
    Handle login requests.
    Request form must include:
    - username: str (can be username or email)
    - password: str

    On success, returns an access token.\n
    On failure, raises HTTPException with appropriate status code and detail.
    """

    # Check if user exists by username or email
    user = await account.getUserByUsername(request.username, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Verify password
    credentials = db.query(models.Credentials).filter(models.Credentials.user_id == user.user_id).first()
    isCorrectPassword = bcrypt.checkpw(request.password.encode('utf-8'), credentials.password_hash.encode('utf-8'))
    if isCorrectPassword == False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    # Create and return access token
    # Token-per-device login, each device is assigned a UUID for management. 
    jti = str(uuid.uuid4())
    access_token = account.createToken(
        data={
            "sub": str(user.user_id),
            "jti": jti
        },
        expires_delta=timedelta(minutes=Duration.ACCESS_TOKEN_EXPIRE_MINUTES),
        secret_key=Encryption.SECRET_ACCESS_KEY
    )
    refresh_token = account.createToken(
        data={
            "sub": str(user.user_id),
            "jti": jti
        },
        expires_delta=timedelta(days=Duration.REFRESH_TOKEN_EXPIRE_DAYS),
        secret_key=Encryption.SECRET_REFRESH_KEY
    )
    now = datetime.now(timezone.utc)
    rftoken = models.RefreshToken(
        user_id=user.user_id,
        jti=jti,
        created_at=now,
        expires_at=now + timedelta(days=Duration.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(rftoken)
    db.commit()
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: Annotated[RegisterRequest, Form()], db: Db_dependency):
    """
    Handle user registration requests.
    Request body must include:
    - username: str
    - password: str
    - email: str\n
    On success, an email verification mail will be sent to user.\n
    On failure, return status code with detail.
    """

    # Check if username or email already exists
    user = await account.getUserByUsername(request.username, db)
    if user is None:
        await account.getUserByUsername(request.email, db)
    if user is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already exists")
    
    # Hash the password
    salt = bcrypt.gensalt()
    pwhash = bcrypt.hashpw(request.password.encode('utf-8'), salt)
    
    # Create new user and credentials
    now = datetime.now(timezone.utc)
    new_user = models.User(
        username=request.username,
        email=request.email,
        bio=None,
        avatar_url=None,
        email_verified_at=None,
        created_at=now,
        updated_at=now
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    new_credentials = models.Credentials(
        user_id=new_user.user_id,
        password_hash=pwhash,
        hash_algorithm=Encryption.HASH_ALGORITHM
    )
    db.add(new_credentials)
    db.commit()

    # Send account verification OTP
    otp = account.generateOtp(new_user.username, OTP_Purpose.OTP_REGISTER, db)
    await mailer.sendOtpMail(otp.otp_code, new_user.username, new_user.email, mailer.REGISTER)
    
    # Automatically log in the user after registration
    login_tokens = await login(OAuth2PasswordRequestForm(username=request.username, password=request.password, scope=""), db)

    return login_tokens

@router.post("/register/verify", status_code=status.HTTP_200_OK)
async def verify_account(this_user: Annotated[models.User, Depends(account.getUserFromToken)], otp: str, db: Db_dependency):
    """
    Verify email address of newly created account.
    """

    # If this user's email address is verified, tell user to not verify again
    if this_user.email_verified_at != None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email verified before")

    # Validate OTP
    await account.validateOtp(otp, this_user.username, OTP_Purpose.OTP_REGISTER, db)

    # If OTP is valid, update email verified status
    this_user.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Email has been verified successfully."
    }

@router.post("/register/resend", status_code=status.HTTP_200_OK)
async def resend_verification_email(this_user: Annotated[models.User, Depends(account.getUserFromToken)], db: Db_dependency):
    # If this user's email address is verified, tell user to not verify again
    if this_user.email_verified_at != None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email verified before")
    
    otp = account.generateOtp(this_user.username, OTP_Purpose.OTP_REGISTER, db)
    await mailer.sendOtpMail(otp.otp_code, this_user.username, this_user.email, mailer.REGISTER)

    return {
        "message": "Verification email resent"
    }

@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_access_token(rf_token: str, db: Db_dependency):
    payload = account.validateToken(rf_token, Encryption.SECRET_REFRESH_KEY)
    record = db.query(models.RefreshToken).filter(
        models.RefreshToken.jti == payload.get("jti"),
        models.RefreshToken.user_id == payload.get("user_id"),
        models.RefreshToken.expires_at > datetime.now(datetime.timezone.utc),
        models.RefreshToken.is_revoked == False
    ).first()

    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    access_token = account.createToken(
        data={
            "sub": str(record.user_id),
            "jti": record.jti,
        },
        expires_delta=Duration.ACCESS_TOKEN_EXPIRE_MINUTES,
        secret_key=Encryption.SECRET_ACCESS_KEY
    )
    return {
        "message": "Token refreshed",
        "access_token": access_token
    }

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(token: Annotated[str, Depends(account.oauth2_scheme)], db: Db_dependency):
    """Handle user logout by invalidating tokens."""

    payload = account.validateToken(token, Encryption.SECRET_ACCESS_KEY)

    print(payload)
    # Get device UUID as JTI in token to determine which device to be logged out.
    jti = payload.get("jti")
    user_id = payload.get("sub")
    if jti is None or user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    
    # Get refresh token corresponding to the device sending request
    record = db.query(models.RefreshToken).filter(
        models.RefreshToken.jti == jti,
        models.RefreshToken.user_id == int(user_id),
    ).first()

    if record is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not found")
    
    # Revoke refresh token in database
    if record.is_revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    
    record.is_revoked = True
    db.commit()

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
    
    otp = account.generateOtp(user.username, OTP_Purpose.OTP_PASSWORD_RESET, db)

    # Send recovery email
    await mailer.sendOtpMail(otp, user.username, user.email, mailer.PASSWORD_RESET)

    return {"message": "Recovery email sent"}

@router.post("/recover/verify")
async def verify_recovery_code(otp: str, username: str, db: Db_dependency):
    record = account.validateOtp(otp, username, OTP_Purpose.OTP_PASSWORD_RESET, db)
    reset_token = account.createToken(
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
    # Validate the reset token
    payload = account.validateToken(token, Encryption.SECRET_RESET_KEY)
    record = db.query(models.OTP).filter(
        models.OTP.jti == payload.get("jti"),
        models.OTP.username == payload.get("sub"),
        models.OTP.purpose == OTP_Purpose.OTP_PASSWORD_RESET,
    ).first()

    if record is None or record.is_token_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    credentials = db.query(models.Credentials).join(models.User).filter(models.User.username == record.username).first()
    
    salt = bcrypt.gensalt()
    pwhash = bcrypt.hashpw(new_password.encode('utf-8'), salt)
    
    credentials.password_hash = pwhash
    credentials.hash_algorithm = Encryption.HASH_ALGORITHM
    db.commit()
    
    return {"message": "Password reset successful"}