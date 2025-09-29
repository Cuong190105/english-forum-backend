import jwt
from database.database import Db_dependency
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta, timezone
from typing import Annotated
from database import models
from random import randint
from configs.config_auth import Encryption, Duration
import uuid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def getUserByUsername(username: str, db: Db_dependency):
    """
    Get user ID by username.\n
    Returns user ID if found, else -1.
    """
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        user = db.query(models.User).filter(models.User.email == username).first()
    return user

def createToken(data: dict, expires_delta: timedelta, secret_key: str):
    """Generate a JWT token."""

    # Copy data to avoid modifying the original dictionary
    # to_encode: dict using TokenData model
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})

    # Generate the JWT token
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=Encryption.ALGORITHM)
    return encoded_jwt

def validateToken(token: str, secret_key: str):
    """
    Check if the token is valid and not expired.\n
    Return token payload on success.\n
    Raise HTTPException if invalid or expired.
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[Encryption.ALGORITHM])
        exp = payload.get("exp")
        if exp is None or datetime.fromtimestamp(exp) < datetime.now(datetime.timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        return payload
    except jwt.exceptions.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

async def validateRefreshToken(token: str, db: Db_dependency):
    payload = validateToken(token)
    user_id = db.query(models.RefreshToken).filter(
        models.RefreshToken.jti == payload.get("jti"),
        models.RefreshToken.expires_at > datetime.now(timezone.utc),
        models.RefreshToken.is_revoked == False
    ).first()

    if user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    
    return user_id

async def getUserFromToken(token: Annotated[str, Depends(oauth2_scheme)], db: Db_dependency):
    """
    Get the current user from the JWT token.
    """
    
    # Decode the JWT token and extract the user ID
    payload = validateToken(token, Encryption.SECRET_ACCESS_KEY)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    # Fetch the user from the database
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

def otpGenerator(username: str, purpose: str, db: Db_dependency):
    """
    Generate an OTP for security purposes.\n
    username: username from user requesting OTP.\n
    purpose: select from OTP_Purpose Enums.\n
    Return OTP object on success.
    """

    # Invalidate any existing token for password reset
    # User can only request a new OTP after 1 minute.
    existing_otp = db.query(models.OTP).filter(
        models.OTP.username == username,
        models.OTP.purpose == purpose,
    ).first()

    if existing_otp is not None:
        if existing_otp.created_at + timedelta(minutes=Duration.OTP_RESEND_INTERVAL_MINUTES) > datetime.now(datetime.timezone.utc):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too soon to request a new OTP")
        else:
            existing_otp.is_token_used = True
            db.commit()
    
    # Generate a recovery OTP
    otp_code = str(randint(0, 999999)).left(6, '0')
    otp = models.OTP(
        username=username,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=Duration.OTP_EXPIRE_MINUTES),
        otp_code=otp_code,
        uuid=str(uuid.uuid4()),
        purpose=purpose,
        trials=Duration.OTP_MAX_TRIALS,
        is_token_used=False
    )
    db.add(otp)
    db.commit()

    return otp

async def validateOtp(otp: str, username: str, purpose: str, db: Db_dependency):
    """
    Validate OTP for certain requests.\n
    Return OTP object on success.
    """

    # Look for the valid record of OTP in database
    record = db.query(models.OTP).filter(
        models.OTP.username == username,
        models.OTP.purpose == purpose,
    ).first()

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No password reset request found")
    
    if record.expires_at < datetime.now(datetime.timezone.utc) or record.trials <= 0 or record.is_token_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")
    
    if record.otp_code != otp:
        record.trials -= 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid OTP. {record.trials} attempts left")
    
    # Invalidate the OTP after successful verification
    record.trials = 0
    db.commit()
    
    return record