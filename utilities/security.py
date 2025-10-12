import bcrypt
from fastapi import HTTPException, status
from configs.config_auth import Encryption, Duration
from database import models
from database.database import Db_dependency
from datetime import datetime, timedelta, timezone
import jwt
from random import randint
import uuid

def createToken(data: dict, expires_delta: timedelta, secret_key: str):
    """
    Generate a JWT token.

    Params:
        data: Token payload content.
        expires_delta: Token time-to-live
        secret_key: A secret key corresponding to each JWT type.

    Returns:
        str: JWT string.
    """

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
    Check if the token is valid and not expired.

    Params:
        token: JWT string
        secret_key: A secret key corresponding to each JWT type.
    Returns:
        dict: token payload on success.
    """
    try:

        payload = jwt.decode(jwt=token, key=secret_key, algorithms=[Encryption.ALGORITHM])
        exp = payload.get("exp")
        if exp is None or datetime.fromtimestamp(exp, timezone.utc) < datetime.now(timezone.utc):
            return None
        return payload
    except jwt.exceptions.InvalidTokenError as e:
        return None
    
async def createRefreshToken(db: Db_dependency, user: models.User) -> models.RefreshToken:
    """
    Create and store user refresh token info.

    Params:
        db: Database session object.
        user: User info.

    Returns:
        str: JWT refresh token
    """

    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    rftoken = models.RefreshToken(
        user_id=user.user_id,
        jti=jti,
        created_at=now,
        expires_at=now + timedelta(days=Duration.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(rftoken)
    db.commit()

    rftoken = createToken(
        data={
            "sub": str(user.user_id),
            "jti": rftoken.jti
        },
        expires_delta=timedelta(days=Duration.REFRESH_TOKEN_EXPIRE_DAYS),
        secret_key=Encryption.SECRET_REFRESH_KEY
    )

    return rftoken

async def getRefreshTokenRecord(db: Db_dependency, payload: dict):
    """
    Get refresh token record from database with data in JWT payload.

    Params:
        db: Database session object.
        payload: JWT payload

    Returns:
        models.RefreshToken: The record if found and valid, otherwise None.
    """

    # Get data and find a match record in database
    jti = payload.get("jti")
    sub = payload.get("sub")

    record = db.query(models.RefreshToken).filter(models.RefreshToken.jti == jti).first()
    if record is None or record.user_id != int(sub) or record.is_revoked:
        return None
    
    return record

async def createAccessToken(db: Db_dependency, refresh_token: str):
    """
    Create an access token.

    Params:
        db: Database session object.
        user: User info

    Returns:
        Optional[str]: JWT access token. If refresh token is invalid, return None.
    """

    # Validate token
    payload = validateToken(refresh_token, Encryption.SECRET_REFRESH_KEY)
    if payload is None:
        return None
    
    record = await getRefreshTokenRecord(db, payload)
    if record is None:
        return None
    
    # Create token
    access_token = createToken(
        data={
            "sub": str(record.user_id),
            "jti": record.jti,
        },
        expires_delta=timedelta(minutes=Duration.ACCESS_TOKEN_EXPIRE_MINUTES),
        secret_key=Encryption.SECRET_ACCESS_KEY
    )

    return access_token

async def invalidateRefreshToken(db: Db_dependency, token: str):
    """
    Cancel Refresh Token on logout.

    Params:
        db: Database session object.
        token: JWT access token string.

    Returns:
        bool: True if token invalidated, else False.
    """

    payload = validateToken(token, Encryption.SECRET_ACCESS_KEY)
    if payload is None:
        return False

    record = await getRefreshTokenRecord(db, payload)
    if record is None:
        return False

    record.is_revoked = True
    db.commit()

    return True

def generateOtp(username: str, purpose: str, db: Db_dependency):
    """
    Generate an OTP for security purposes.

    Params:
        username: username of user requesting OTP.
        purpose: select from `OTP_Purpose` Enums.

    Returns:
        OTP: OTP object on success.
    """

    # Invalidate any existing token for password reset
    # User can only request a new OTP after 1 minute.
    existing_otp = db.query(models.OTP).filter(
        models.OTP.username == username,
        models.OTP.purpose == purpose,
    ).first()

    if existing_otp is not None:
        # Temporarily use this method to limit request. Improve later
        if existing_otp.created_at.replace(tzinfo=timezone.utc) + timedelta(minutes=Duration.OTP_RESEND_INTERVAL_MINUTES) > datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too soon to request a new OTP")
        else:
            existing_otp.is_token_used = True
            db.commit()
    
    # Generate a recovery OTP
    now=datetime.now(timezone.utc)
    otp_code = str(randint(0, 999999)).ljust(6, '0')
    otp = models.OTP(
        username=username,
        created_at=now,
        expires_at=now + timedelta(minutes=Duration.OTP_EXPIRE_MINUTES),
        otp_code=otp_code,
        jti=str(uuid.uuid4()),
        purpose=purpose,
        trials=Duration.OTP_MAX_TRIALS,
        is_token_used=False
    )
    db.add(otp)
    db.commit()

    return otp

async def validateOtp(otp: str, username: str, purpose: str, db: Db_dependency):
    """
    Validate OTP for certain requests.

    Params:
        otp: OTP code
        username: User's username
        purpose: Security purpose of this OTP, selected from `OTP_Purpose` enum.
        db: Database session object

    Returns:
        Optional[OTP]: OTP object on success. Otherwise return None
    """

    # Look for the valid record of OTP in database
    record = db.query(models.OTP).filter(
        models.OTP.username == username,
        models.OTP.purpose == purpose,
    ).order_by(models.OTP.expires_at.desc()).first()

    if record is None:
        return None
    
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc) or record.trials <= 0 or record.is_token_used:
        return None

    if record.otp_code != otp:
        record.trials -= 1
        db.commit()
        return None
    
    # Invalidate the OTP after successful verification
    record.is_token_used = True
    record.trials = 0
    db.commit()
    
    return record

def hashPassword(password: str):
    """
    Hash plain password

    Params:
        password: Plain password string.
    
    Returns:
        str: Hashed password string
    """

    salt = bcrypt.gensalt()
    pwhash = bcrypt.hashpw(password.encode('utf-8'), salt)

    return pwhash

async def verifyPassword(user: models.User, password: str):
    """
    Check if given password matches hashed password in DB.

    Params:
        user: User object.
        password: Plain password string.

    Returns:
        bool: `True` if 2 passwords match, otherwise `False`.
    """
    hashed_password = user.credential.password_hash
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

async def cancelEmailChangeRequest(db: Db_dependency, token: str):
    """
    Cancel email change.
    Params:
        db: Database session object
        token: JWT token to invalidate request
    
    Returns:
        bool: True if request cancelled, else False
    """
    payload = validateToken(token, Encryption.SECRET_RESET_KEY)
    request = db.query(models.EmailChangeRequest).filter(models.EmailChangeRequest.jti == payload.get("jti")).first()
    if request is None:
        return False
    
    request.is_revoked = True
    db.commit()