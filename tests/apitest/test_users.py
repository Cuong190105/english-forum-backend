from datetime import timedelta
import pytest
from database.models import User, OTP
from configs.config_auth import OTP_Purpose, Encryption
from utilities.security import createToken

async def mock_send_email(subject: str, content: str, target: str):
    corrent_email = ["email1@example.com", "email2@example.com", "newemail1@example.com"]
    if target not in corrent_email:
        raise Exception("Failed to send email to " + target)

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestUser:

    @pytest.mark.asyncio
    async def test_getCurrentUser(self, async_client):
        response = await async_client.get(
            "/user",
            headers={"Authorization": "Bearer 1"}
        )
        
        assert response.status_code == 200
        assert response.json().get("username") == "testuser1"

        # Test invalid token
        response = await async_client.get(
            "/user",
            headers={"Authorization": "Bearer 9999"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_getUserByUsername(self, async_client):
        response = await async_client.get(
            "/user/testuser1",
            headers={"Authorization": "Bearer 1"},
        )
        
        assert response.status_code == 200
        assert response.json().get("username") == "testuser1"

        response = await async_client.get(
            "/user/testuser2",
            headers={"Authorization": "Bearer 1"},
        )
        
        assert response.status_code == 200
        assert response.json().get("username") == "testuser2"

        # Test not existed user
        response = await async_client.get(
            "/user/testuser3",
            headers={"Authorization": "Bearer 1"},
        )
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_updateBio(self, async_client):
        # Test normal
        response = await async_client.put(
            "/user/bio",
            headers={"Authorization": "Bearer 1"},
            data={"bio": "Test bio"}
        )
        assert response.status_code == 200
        
        # Test invalid
        response = await async_client.put(
            "/user/bio",
            headers={"Authorization": "Bearer 1"},
            data={"bio": ""}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_updateUsername(self, async_client):
        # Test normal
        response = await async_client.put(
            "/user/username",
            headers={"Authorization": "Bearer 2"},
            data={"username": "newtestuser2"}
        )
        assert response.status_code == 200
        
        # Test invalid
        response = await async_client.put(
            "/user/username",
            headers={"Authorization": "Bearer 2"},
            data={"username": ""}
        )
        assert response.status_code == 422
        
        # Test duplicate
        response = await async_client.put(
            "/user/username",
            headers={"Authorization": "Bearer 2"},
            data={"username": "testuser1"}
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_updateEmail(self, async_client, monkeypatch, mock_db):
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)

        # Test duplicate
        response = await async_client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "email2@example.com"}
        )
        assert response.status_code == 409
        
        # Test invalid
        response = await async_client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "asdf"}
        )
        assert response.status_code == 422
        
        # Test not existed email
        response = await async_client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "abcd@example.com"}
        )
        assert response.status_code == 500
        
        # Test normal
        response = await async_client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "newemail1@example.com"}
        )
        assert response.status_code == 200

        # Test wrong otp
        r = await async_client.post(
            "/user/email/confirm",
            headers={"Authorization": "Bearer 1"},
            data={"otp": "000000"}
        )
        assert r.status_code == 401

        otp = mock_db.query(OTP).filter(OTP.username == "testuser1", OTP.purpose == OTP_Purpose.OTP_EMAIL_CHANGE, OTP.is_token_used == False).first()
        
        # Test correct
        r = await async_client.post(
            "/user/email/confirm",
            headers={"Authorization": "Bearer 1"},
            data={"otp": otp.otp_code}
        )
        assert r.status_code == 200
        assert mock_db.query(User).filter(User.username == "testuser1").first().email == "newemail1@example.com"

    @pytest.mark.asyncio
    async def test_updatePassword(self, async_client):
        # Test wrong password
        r = await async_client.put(
            "/user/password",
            headers={"Authorization": "Bearer 1"},
            data={
                "password": "testuser1passwd",
                "new_password": "Tedskwke"
            }
        )
        assert r.status_code == 401

        # Test new password invalid
        r = await async_client.put(
            "/user/password",
            headers={"Authorization": "Bearer 1"},
            data={
                "password": "testuser1passwd",
                "new_password": "Twke"
            }
        )
        assert r.status_code == 422

        # Test normal
        r = await async_client.put(
            "/user/password",
            headers={"Authorization": "Bearer 1"},
            data={
                "password": "testuser1password",
                "new_password": "newtestuser1password"
            }
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_cancelEmailChange(self, async_client, monkeypatch):
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)

        response = await async_client.put(
            "/user/email",
            headers={"Authorization": "Bearer 2"},
            data={"email": "email1@example.com"}
        )
        assert response.status_code == 200

        token = createToken(
            data={"user_id": str(2)},
            expires_delta=timedelta(days=365),
            secret_key=Encryption.SECRET_RESET_KEY
        )

        # Test wrong token
        wrongtoken = "faiosdjfioasdfoiasdjfoiajsdof"
        r = await async_client.get("/cancel/emailchange/" + wrongtoken)
        assert r.status_code == 400

        # Test correct token
        r = await async_client.get("/cancel/emailchange/" + token)
        assert r.status_code == 200

        # Test used token
        r = await async_client.get("/cancel/emailchange/" + token)
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_updateAvatar(self, async_client, mock_file):
        # Test normal
        r = await async_client.put(
            "/user/avatar",
            headers={"Authorization": "Bearer 1"},
            files={"new_avatar": mock_file["normal_jpg"]}
        )
        assert r.status_code == 200

        # Test invalid file
        r = await async_client.put(
            "/user/avatar",
            headers={"Authorization": "Bearer 1"},
            files={"new_avatar": mock_file["wrong_type_txt"]}
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_changeRelationship(self, async_client):
        # Test follow
        r = await async_client.post(
            "/user/companion/follow",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 200

        # Test unfollow
        r = await async_client.post(
            "/user/companion/unfollow",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 200

        # Test refollow
        r = await async_client.post(
            "/user/companion/follow",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 200

        # Test self follow
        r = await async_client.post(
            "/user/testuser1/follow",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 403

        # Test invalid user
        r = await async_client.post(
            "/user/nonexistentuser/follow",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_getFollowers(self, async_client):
        # Test get followers
        r = await async_client.get(
            "/user/testuser1/followers",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 200
        r = await async_client.get(
            "/user/nonexistentuser/followers",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_getFollowing(self, async_client):
        # Test get following
        r = await async_client.get(
            "/user/testuser1/following",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 200
        r = await async_client.get(
            "/user/nonexistentuser/following",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_getUserPosts(self, async_client):
        # Test get posts
        r = await async_client.get(
            "/user/testuser1/posts",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 200
        r = await async_client.get(
            "/user/nonexistentuser/posts",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_getUserComments(self, async_client):
        # Test get comments
        r = await async_client.get(
            "/user/testuser1/comments",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 200
        r = await async_client.get(
            "/user/nonexistentuser/comments",
            headers={"Authorization": "Bearer 1"})
        assert r.status_code == 404