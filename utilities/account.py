from database.database import Db_dependency
from datetime import datetime, timedelta, timezone
from database import models
from sqlalchemy import or_
from configs.config_auth import Encryption, OTP_Purpose
from utilities import security, mailer

async def getUserByUsername(username: str, db: Db_dependency):
    """
    Get user by username.

    Parameters:
        username: The username of user. Can be username or email.
        db: Database session object.

    Returns:
        Optional[models.User]: user if found, else None.
    """
    user = db.query(models.User).filter(or_(models.User.username == username, models.User.email == username)).first()
    return user


async def verifyEmail(user: models.User, otp: str, db: Db_dependency):
    """
    Verify user email address.

    Params:
        user: User info
        otp: OTP code
        db: Database session object.
    
    Returns:
        bool: True if verification success, else False.
    """

    otp = await security.validateOtp(otp, user.username, OTP_Purpose.OTP_REGISTER, db)
    
    if otp is not None:
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()

    return otp is not None


async def createNewAccount(db: Db_dependency, username: str, password: str, email: str):
    """
    Add new account to database.

    Params:
        db: Database session object.
        username: User's username.
        password: User's password.
        email: User's email.

    Returns:
        models.User: new user object.
    """

    pwhash = security.hashPassword(password)

    # Create new user and credentials
    now = datetime.now(timezone.utc)
    new_user = models.User(
        username=username,
        email=email,
        bio=None,
        avatar_url=None,
        email_verified_at=None,
        created_at=now,
        updated_at=now
    )

    new_credentials = models.Credentials(
        user_id=new_user.user_id,
        password_hash=pwhash,
        hash_algorithm=Encryption.HASH_ALGORITHM
    )

    new_user.credential = new_credentials
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

async def resetPassword(db: Db_dependency, token: str, new_password: str):
    """
    Reset user password on forget request.

    Params:
        db: Database session object.
        token: JWT password reset token.
        new_password: New password string

    Returns:
        bool: True if password reset, else False 
    """
    payload = security.validateToken(token, Encryption.SECRET_RESET_KEY)
    record = db.query(models.OTP).filter(
        models.OTP.jti == payload.get("jti"),
        models.OTP.username == payload.get("sub"),
        models.OTP.purpose == OTP_Purpose.OTP_PASSWORD_RESET,
    ).first()

    if record is None or record.is_token_used:
        return False
    
    user = getUserByUsername(payload.get("sub"))
    await updatePassword(db, user, new_password)

    return True
    

async def updatePassword(db: Db_dependency, user: models.User, new_password: str):
    """
    Update user's password

    Params:
        db: Database session object
        user: User info
        new_password: New password string

    Returns:
        None
    """

    pwhash = security.hashPassword(new_password)
    user.credential.password_hash = pwhash
    user.credential.hash_algorithm = Encryption.HASH_ALGORITHM
    db.commit()

async def updateUsername(db: Db_dependency, user: models.User, new_username: str):
    """
    Update user's password

    Params:
        db: Database session object
        user: User info
        new_username: New username string

    Returns:
        None
    """

    user.username = new_username
    db.commit()

async def updateBio(db: Db_dependency, user: models.User, new_bio: str):
    """
    Update user's password

    Params:
        db: Database session object
        user: User info
        new_bio: New bio string

    Returns:
        None
    """

    user.bio = new_bio
    db.commit()

async def createEmailChangeRequest(db: Db_dependency, otp: models.OTP, user: models.User, new_email: str):
    """
    Store email change request into database.

    Params:
        db: Database session object.
        otp: OTP info.
        user: User info.
        new_email: New email string.
    
    Returns:
        None
    """

    # For security purpose, send a cancel request link to user's current email.
    jwt = security.createToken(
        data={
            "jti": otp.jti,
            "user_id": user.user_id,
        },
        expires_delta=timedelta(days=365),
        secret_key=Encryption.SECRET_RESET_KEY
    )
    cancel_link = "myapp.com/cancel/emailchange/" + jwt
    await mailer.sendWarningChangingEmailMail(username=user.username, new_email=new_email, target_address=user.email, cancel_link=cancel_link)

    # Add email change token to DB. New email will be updated only after user verify.
    request = models.EmailChangeRequest(
        user_id=user.user_id,
        new_email=new_email,
        jti=otp.jti
    )

    db.add(request)
    db.commit()

async def updateEmail(db: Db_dependency, user: models.User, otp: str):
    """
    Confirm update request and change email address.

    Params:
        db: Database session object.
        user: User info
        otp: OTP code to verify action

    Returns:
        bool: True if email updated, else False
    """

    # Validate OTP and get jti
    record = security.validateOtp(otp, user.username, OTP_Purpose.OTP_EMAIL_CHANGE, db)
    if record is None:
        return False
    
    # Get email change request stored on DB before
    request = db.query(models.EmailChangeRequest).filter(
        models.EmailChangeRequest.jti == record.jti,
        models.EmailChangeRequest.user_id == user.user_id).first()
    
    if request.is_revoked:
        return False
    
    user.email = request.new_email
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    return True