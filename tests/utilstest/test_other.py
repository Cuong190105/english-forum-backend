from io import BytesIO
from fastapi import UploadFile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utilities import attachments
from database.database import Base
from database.models import Post, User, Credentials, OTP, EmailChangeRequest
from configs.config_auth import OTP_Purpose, Encryption, Duration
from datetime import datetime, timedelta, timezone
from utilities import activity, mailer

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestOther:

    @pytest.mark.asyncio
    async def test_getMentionedUser(self, mock_db):
        post = "@username1 @username2 check this out!"
        assert len(await activity.getMentionedUser(post, mock_db)) == 2

    @pytest.mark.asyncio
    async def test_getNotification(self, mock_db):
        user = mock_db.query(User).filter(User.username == "username1").first()
        cursor = datetime.now(timezone.utc)
        assert len(await activity.getNotifications(user, mock_db, cursor, 0)) == 1
    
    @pytest.mark.asyncio
    async def test_markAsRead(self, mock_db):
        user = mock_db.query(User).filter(User.username == "username1").first()
        cursor = datetime.now(timezone.utc)
        assert await activity.markAsRead(mock_db, user, 1) is not None
        assert await activity.markAsRead(mock_db, user, 2) is None
    
    @pytest.mark.asyncio
    async def test_mailer(self, monkeypatch):
        async def fake_send(*args, **kwargs):
            if args[0]["to"] == 'falseaddress':
                raise Exception("Failed to send email")
            return "hi"
        monkeypatch.setattr("aiosmtplib.send", fake_send)

        assert await mailer.sendWarningChangingEmailMail(
            "testusername",
            "testemail",
            "testaddress",
            "testlink"
        ) is None
    
        with pytest.raises(Exception):
            await mailer.sendWarningChangingEmailMail(
                "testusername",
                "testemail",
                "falseaddress",
                "testlink"
            )