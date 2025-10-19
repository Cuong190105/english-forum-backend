from datetime import timedelta
import pytest
from fastapi import HTTPException, Request
from routers.dependencies import getUserFromToken
from utilities.security import createToken
from configs.config_auth import Encryption, Duration
from unittest.mock import Mock

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestDependencies:

    @pytest.mark.asyncio
    async def test_getUserFromToken(self, mock_db):
        token = createToken(
            data={
                "sub": str(1),
                "jti": "uahsdfhiusadhfiuds",
            },
            expires_delta=timedelta(Duration.ACCESS_TOKEN_EXPIRE_MINUTES),
            secret_key=Encryption.SECRET_ACCESS_KEY
        )

        wrongtoken = createToken(
            data={
                "sub": str(999),
                "jti": "uahsdfhiusadhfiuds",
            },
            expires_delta=timedelta(Duration.ACCESS_TOKEN_EXPIRE_MINUTES),
            secret_key=Encryption.SECRET_ACCESS_KEY
        )

        unverifiedtoken = createToken(
            data={
                "sub": str(2),
                "jti": "uahsdfhiusadhfiuds",
            },
            expires_delta=timedelta(Duration.ACCESS_TOKEN_EXPIRE_MINUTES),
            secret_key=Encryption.SECRET_ACCESS_KEY
        )

        request = Mock()
        request.url.path = "/"


        # Test normal request
        assert (await getUserFromToken(token, mock_db, request)).user_id == 1

        # Test wrong token
        with pytest.raises(HTTPException):
            await getUserFromToken("wrongtoken", mock_db, request)

        # Test token containing nonexistent user id
        with pytest.raises(HTTPException):
            await getUserFromToken(wrongtoken, mock_db, request)

        # Test token from unverified user
        with pytest.raises(HTTPException):
            await getUserFromToken(wrongtoken, mock_db, request)

        # Test token from unverified user on special verify routes
        verify_request = Mock()
        verify_request.url.path = "/register/verify"
        assert await getUserFromToken(unverifiedtoken, mock_db, verify_request) is not None

        verify_request.url.path = "/register/resend"
        assert await getUserFromToken(unverifiedtoken, mock_db, verify_request) is not None
