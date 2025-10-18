import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utilities import account, security, user as userutils
from database.database import Base
from database.models import User, Credentials, OTP, EmailChangeRequest
from configs.config_auth import OTP_Purpose, Encryption, Duration
from datetime import datetime, timedelta, timezone

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestAccount:

    @pytest.mark.asyncio
    async def test_getUserByUsername(self, mock_db):
        print(mock_db.query(User).all())
        user1 = await userutils.getUserByUsername("username1", mock_db)
        user2 = await userutils.getUserByUsername("username2", mock_db)
        user3 = await userutils.getUserByUsername("username3", mock_db)

        # Check if user can be queried
        assert user1 is not None
        assert type(user2) == User

        # Check if function returns correctly when user not found
        assert user3 is None

        # Check if info is retrieved correctly
        assert user1.user_id == 1
        assert user2.email_verified_at is None

    # def test_verifyEmail():
    #     pass

    @pytest.mark.asyncio
    async def test_createNewAccount(self, mock_db):
        user3 = await account.createNewAccount(mock_db, "username3", "username3", "username3@example.com")
        user2 = await account.createNewAccount(mock_db, "username2", "username2", "username3@example.com")
        user1 = await account.createNewAccount(mock_db, "username4", "username2", "username1@example.com")

        # Check if function returns correct value
        assert type(user3) == User

        # Check if user info is correct
        assert user3.username == "username3"

        # Check if user info is written to db
        assert await userutils.getUserByUsername("username3", mock_db) is not None

        # Check if function returns None on exception
        assert user2 is None
        assert user1 is None

    @pytest.mark.asyncio
    async def test_updateBasicInfo(self, mock_db):
        user1 = await userutils.getUserByUsername("username1", mock_db)
        await account.updateBio(mock_db, user1, "new bio")
        await account.updateUsername(mock_db, user1, "username11")

        # Check if info is updated correctly
        assert user1.bio == "new bio"
        assert user1.username == "username11"

        user12 = await userutils.getUserByUsername("username1", mock_db)
        assert user12 is None
        user11 = await userutils.getUserByUsername("username11", mock_db)
        assert user11 is not None
        assert user11.user_id == user1.user_id
        assert user11.bio == "new bio"

        # Check if function handles exception
        await account.updateUsername(mock_db, user1, "username2")
        assert user1.username == "username11"

    @pytest.mark.asyncio
    async def test_otp(self, mock_db):
        # Check if otp object is created and written to db
        otp = await security.generateOtp("username2", OTP_Purpose.OTP_REGISTER, mock_db)
        assert otp is not None
        assert mock_db.query(OTP).filter(OTP.otp_id == otp.otp_id).first() is not None

        # Check if validate function can get otp record if valid otp code is provided
        valid_otp = await security.validateOtp(otp.otp_code, "username2", OTP_Purpose.OTP_REGISTER, mock_db)
        assert valid_otp is not None

        invalid_otp1 = await security.validateOtp(otp.otp_code, "username1", OTP_Purpose.OTP_REGISTER, mock_db)
        invalid_otp2 = await security.validateOtp(otp.otp_code, "username2", OTP_Purpose.OTP_EMAIL_CHANGE, mock_db)
        invalid_otp3 = await security.validateOtp("123456", "username2", OTP_Purpose.OTP_REGISTER, mock_db)
        invalid_otp4 = await security.validateOtp("12df12", "username2", OTP_Purpose.OTP_REGISTER, mock_db)
        invalid_otp5 = await security.validateOtp("1212", "username2", OTP_Purpose.OTP_REGISTER, mock_db)
        assert invalid_otp1 is None
        assert invalid_otp2 is None
        assert invalid_otp3 is None
        assert invalid_otp4 is None
        assert invalid_otp5 is None

        # Check if function handles expired otp correctly
        otp1 = await security.generateOtp("username1", OTP_Purpose.OTP_REGISTER, mock_db)
        otp2 = await security.generateOtp("username1", OTP_Purpose.OTP_LOGIN, mock_db)
        otp3 = await security.generateOtp("username1", OTP_Purpose.OTP_PASSWORD_RESET, mock_db)
        otp1.trials = 0
        otp2.expires_at = datetime.now(timezone.utc)
        otp3.is_token_used = True
        mock_db.commit()

        assert await security.validateOtp(otp1.otp_code, "username1", OTP_Purpose.OTP_REGISTER, mock_db) is None
        assert await security.validateOtp(otp2.otp_code, "username1", OTP_Purpose.OTP_LOGIN, mock_db) is None
        assert await security.validateOtp(otp3.otp_code, "username1", OTP_Purpose.OTP_PASSWORD_RESET, mock_db) is None

        # Check if otp generator limits otp gen rate correctly
        assert await security.generateOtp("username1", OTP_Purpose.OTP_REGISTER, mock_db) is None
        assert await security.generateOtp("username1", OTP_Purpose.OTP_LOGIN, mock_db) is None
        # limit will not apply to otp with is_token_used set to true
        assert await security.generateOtp("username1", OTP_Purpose.OTP_PASSWORD_RESET, mock_db) is not None


    @pytest.mark.asyncio
    async def test_updateEmail(self, mock_db):
        user = await userutils.getUserByUsername("username2", mock_db)
        otp = await security.generateOtp("username2", OTP_Purpose.OTP_EMAIL_CHANGE, mock_db)
        await account.createEmailChangeRequest(mock_db, otp, user, "user2@example.com", True)

        # Check if email change request is created and written to db
        request = mock_db.query(EmailChangeRequest).filter(
            EmailChangeRequest.user_id == user.user_id,
            EmailChangeRequest.new_email == "user2@example.com",
            EmailChangeRequest.is_revoked == False,
        ).first()
        assert request is not None

        # Check if function handles resend request correctly
        otp.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        mock_db.commit()
        otp = await security.generateOtp("username2", OTP_Purpose.OTP_EMAIL_CHANGE, mock_db)
        await account.createEmailChangeRequest(mock_db, otp, user, "user2@example.com", True)
        mock_db.refresh(request)
        assert request.jti == otp.jti

        # Check if update email function works correctly
        assert await account.updateEmail(mock_db, user, "wrongotp") is False
        assert await account.updateEmail(mock_db, user, otp.otp_code) is True
        mock_db.refresh(user)
        assert user.email == "user2@example.com"

        # Check if email change request is revoked correctly
        mock_db.refresh(request)
        assert request.is_revoked is True

        otp = await security.generateOtp("username3", OTP_Purpose.OTP_EMAIL_CHANGE, mock_db)
        user3 = await userutils.getUserByUsername("username3", mock_db)
        await account.createEmailChangeRequest(mock_db, otp, user3, "user3@example.com", True)

        jwt = security.createToken(
            data={
                "user_id": str(user3.user_id),
            },
            expires_delta=timedelta(days=365),
            secret_key=Encryption.SECRET_RESET_KEY
        )
        wrong_jwt1 = security.createToken(
            data={
                "user_id": str(user3.user_id),
            },
            expires_delta=timedelta(days=3),
            secret_key=Encryption.SECRET_RESET_KEY
        )
        wrong_jwt2 = security.createToken(
            data={
                "user_id": str(user3.user_id),
            },
            expires_delta=timedelta(days=3),
            secret_key=Encryption.SECRET_ACCESS_KEY
        )
        wrong_jwt3 = security.createToken(
            data={
                "user_id": str(user.user_id),
            },
            expires_delta=timedelta(days=365),
            secret_key=Encryption.SECRET_RESET_KEY
        )
        assert await security.cancelEmailChangeRequest(mock_db, jwt) is True
        assert await security.cancelEmailChangeRequest(mock_db, wrong_jwt1) is False
        assert await security.cancelEmailChangeRequest(mock_db, wrong_jwt2) is False
        assert await security.cancelEmailChangeRequest(mock_db, wrong_jwt3) is False

    @pytest.mark.asyncio
    async def test_updatePassword(self, mock_db):
        user = await userutils.getUserByUsername("username11", mock_db)
        await account.updatePassword(mock_db, user, "newpassword") is False

        # Check if password is updated correctly
        assert security.verifyPassword("newpassword", user.credential.password_hash) is True
        assert security.verifyPassword("username1", user.credential.password_hash) is False

        # Check if reset password works correctly
        otp = await security.generateOtp("username11", OTP_Purpose.OTP_PASSWORD_RESET, mock_db)
        token = security.createToken(
            data={"sub": user.username, "jti":otp.jti},
            expires_delta=timedelta(minutes=Duration.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            secret_key=Encryption.SECRET_RESET_KEY
        )
        assert await account.resetPassword(mock_db, token, "resetpassword") is True
        assert security.verifyPassword("resetpassword", user.credential.password_hash) is True
    
    @pytest.mark.asyncio
    async def test_verifyEmail(self, mock_db):
        user = mock_db.query(User).filter(User.user_id == 1).first()
        user.email_verified_at = None

        otp = OTP(
            username=user.username,
            otp_code="123456",
            jti="asdfasdf",
            purpose=OTP_Purpose.OTP_REGISTER,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
        )

        mock_db.add(otp)
        mock_db.commit()

        assert await account.verifyEmail(user, "000000", mock_db) is False
        assert user.email_verified_at is None
        assert await account.verifyEmail(user, otp.otp_code, mock_db) is True
        assert user.email_verified_at is not None