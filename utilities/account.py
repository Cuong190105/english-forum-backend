from database.database import Db_dependency
from datetime import datetime, timedelta, timezone
from database import models
from sqlalchemy import or_, exc
from configs.config_auth import Encryption, OTP_Purpose
from utilities import security, mailer, user as userutils
from configs.config_app import APP_URL

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
    
    if otp is None:
        return False
    
    user.email_verified_at = datetime.now(timezone.utc)
    await security.invalidateOtp(db, otp)
    db.commit()
    return True

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
    )

    new_credentials = models.Credentials(
        password_hash=pwhash,
        hash_algorithm=Encryption.HASH_ALGORITHM
    )

    new_user.credential = new_credentials

    # Try to add new user to database. Although username uniqueness is checked before, this add another layer if admin or developer accidentally makes mistake.
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except exc.IntegrityError:
        db.rollback()
        return None
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
    if payload == None:
        return False

    record = db.query(models.OTP).filter(
        models.OTP.jti == payload.get("jti"),
        models.OTP.username == payload.get("sub"),
        models.OTP.purpose == OTP_Purpose.OTP_PASSWORD_RESET,
    ).first()

    if record is None or record.is_token_used:
        return False
    
    user = await userutils.getUserByUsername(payload.get("sub"), db)
    await updatePassword(db, user, new_password)
    record.is_token_used = True
    db.commit()

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
    Update user's username

    Params:
        db: Database session object
        user: User info
        new_username: New username string

    Returns:
        None
    """

    try:
        user.username = new_username
        db.commit()
    except exc.IntegrityError:
        db.rollback()

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

async def createEmailChangeRequest(db: Db_dependency, otp: models.OTP, user: models.User, new_email: str, debug: bool = False):
    """
    Store email change request into database.

    Params:
        db: Database session object.
        otp: OTP info.
        user: User info.
        new_email: New email string.
        debug: If True, skip sending email.
    
    Returns:
        None
    """

    # If request already exists, update otp only
    existing_request = db.query(models.EmailChangeRequest).filter(
        models.EmailChangeRequest.user_id == user.user_id,
        models.EmailChangeRequest.new_email == new_email,
        models.EmailChangeRequest.is_revoked == False
    ).first()

    if existing_request is not None:
        existing_request.jti = otp.jti
        existing_request.created_at = datetime.now(timezone.utc)
        db.commit()
        return None

    # For security purpose, send a cancel request link to user's current email.
    if not debug:
        jwt = security.createToken(
            data={
                "user_id": str(user.user_id),
            },
            expires_delta=timedelta(days=365),
            secret_key=Encryption.SECRET_RESET_KEY
        )
        cancel_link = APP_URL + "/cancel/emailchange/" + jwt
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
    record = await security.validateOtp(otp, user.username, OTP_Purpose.OTP_EMAIL_CHANGE, db)
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
    request.is_revoked = True
    db.commit()

    return True