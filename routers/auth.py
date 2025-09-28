from random import random
import uuid
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from database.database import Db_dependency
from database import models
import bcrypt
from datetime import datetime, timedelta
from typing import Annotated
from utilities import auth_helper, mailer
from configs.config_auth import *

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str

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
    user = await auth_helper.getUserByUsername(request.username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Verify password
    credentials = db.query(models.Credentials).filter(models.Credentials.user_id == user.user_id).first()
    isCorrectPassword = bcrypt.checkpw(request.password.encode('utf-8'), credentials.password_hash.encode('utf-8'))
    if isCorrectPassword == False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    # Create and return access token
    access_token = auth_helper.createToken(
        data={"sub": user.user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        secret_key=SECRET_ACCESS_KEY
    )
    refresh_token = auth_helper.createToken(
        data={"sub": user.user_id},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        secret_key=SECRET_REFRESH_KEY
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: Db_dependency):
    """
    Handle user registration requests.
    Request body must include:
    - username: str
    - password: str
    - email: str
    On success, 
    """

    # Check if username or email already exists
    user = await auth_helper.getUserByUsername(request.username)
    if user is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already exists")
    
    # Hash the password
    salt = bcrypt.gensalt()
    pwhash = bcrypt.hashpw(request.password.encode('utf-8'), salt)
    
    # Create new user and credentials
    new_user = models.User(
        username=request.username,
        email=request.email,
        bio=None,
        avatar_url=None,
        email_verified_at=None,
        created_at=None,
        updated_at=None
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    new_credentials = models.Credentials(
        user_id=new_user.user_id,
        password_hash=pwhash,
        hash_algorithm=HASH_ALGORITHM
    )
    db.add(new_credentials)
    db.commit()
    
    # Automatically log in the user after registration
    access_token = await login(OAuth2PasswordRequestForm(username=request.username, password=request.password, scope=""), db)

    return access_token

@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refreshAccessToken(token: Annotated[str, Depends(auth_helper.oauth2_scheme)]):
    user_id = await auth_helper.validateRefreshToken(token)
    access_token = auth_helper.createToken(
        data={"sub":user_id},
        expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES,
        secret_key=SECRET_ACCESS_KEY
    )
    return {
        "message": "Token refreshed",
        "access_token": access_token
    }

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(access_token: Annotated[str, Depends(auth_helper.oauth2_scheme)], refresh_token: Annotated[str, Depends(auth_helper.oauth2_scheme)], db: Db_dependency):
    """Handle user logout by invalidating tokens."""

    # Validate request
    access_payload = auth_helper.validateToken(access_token, SECRET_ACCESS_KEY)
    refresh_payload = auth_helper.validateToken(refresh_token, SECRET_REFRESH_KEY)
    if access_payload.get("sub") != refresh_payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tokens do not match")
    
    # Revoke refresh token in database
    token_record = db.query(models.RefreshToken).filter(models.RefreshToken.token == refresh_token).first()
    if token_record.is_revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invaild")
    
    token_record.is_revoked = True
    db.commit()

    return {"message": "Logout successful"}
    
@router.post("/recover", status_code=status.HTTP_200_OK)
async def recoverPassword(username: str, db: Db_dependency):
    """
    Handle password recovery requests.\n
    If the username or email exists, send a recovery email.
    """
    
    # Check if user exists by username or email and then get user ID
    user = await auth_helper.getUserByUsername(username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Invalidate any existing token for password reset
    existing_otp = db.query(models.OTP).filter(
        models.OTP.username == username,
        models.OTP.purpose == OTP_PASSWORD_RESET,
    ).first()
    if existing_otp and existing_otp.created_at + timedelta(minutes=OTP_RESEND_INTERVAL_MINUTES) < datetime.now(datetime.timezone.utc) :
        existing_otp.is_token_used = True
        db.commit()
    
    # Generate a recovery OTP
    otp = str(random.randint(0, 999999)).left(6, '0')
    recovery_otp = models.OTP(
        username=username,
        expires_at=datetime.now(datetime.timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES),
        otp_code=otp,
        uuid=str(uuid.uuid4()),
        purpose=OTP_PASSWORD_RESET,
        trials=OTP_MAX_TRIALS,
        is_token_used=False
    )
    db.add(recovery_otp)
    db.commit()

    # Send recovery email
    await mailer.sendOtpMail(otp, user.username, user.email, mailer.PASSWORD_RESET)

    return {"message": "Recovery email sent"}

@router.post("/recover/verify")
async def verifyRecoveryCode(code: str, username: str, db: Db_dependency):
    # Look for the valid record of password reset OTP in database
    record = db.query(models.OTP).filter(
        models.OTP.username == username,
        models.OTP.purpose == OTP_PASSWORD_RESET,
    ).first()

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No password reset request found")
    
    if record.expires_at < datetime.now(datetime.timezone.utc) or record.trials <= 0 or record.is_token_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")
    
    if record.otp_code != code:
        record.trials -= 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid OTP. {record.trials} attempts left")
    
    # Invalidate the OTP after successful verification
    record.trials = 0
    db.commit()
    reset_token = auth_helper.createToken(
        data={"sub": record.username, "jti": record.jti},
        expires_delta=timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        secret_key=SECRET_RESET_KEY
    )

    return {
        "message": "OTP verified",
        "reset_token": reset_token
    }

@router.post("/reset")
async def resetPassword(token: str, new_password: str, db: Db_dependency):
    # Validate the reset token
    payload = auth_helper.validateToken(token, SECRET_RESET_KEY)
    record = db.query(models.OTP).filter(
        models.OTP.jti == payload.get("jti"),
        models.OTP.username == payload.get("sub"),
        models.OTP.purpose == OTP_PASSWORD_RESET,
    ).first()

    if record is None or record.is_token_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    credentials = db.query(models.Credentials).join(models.User).filter(models.User.username == record.username).first()
    
    salt = bcrypt.gensalt()
    pwhash = bcrypt.hashpw(new_password.encode('utf-8'), salt)
    
    credentials.password_hash = pwhash
    credentials.hash_algorithm = HASH_ALGORITHM
    db.commit()
    
    return {"message": "Password reset successful"}