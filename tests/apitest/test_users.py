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

    def test_getCurrentUser(self, client):
        response = client.get(
            "/user",
            headers={"Authorization": "Bearer 1"}
        )
        
        assert response.status_code == 200
        assert response.json().get("username") == "testuser1"

        # Test invalid token
        response = client.get(
            "/user",
            headers={"Authorization": "Bearer 3"}
        )
        assert response.status_code == 401

    def test_getUserByUsername(self, client):
        response = client.get(
            "/user/testuser1",
            headers={"Authorization": "Bearer 1"},
        )
        
        assert response.status_code == 200
        assert response.json().get("username") == "testuser1"

        response = client.get(
            "/user/testuser2",
            headers={"Authorization": "Bearer 1"},
        )
        
        assert response.status_code == 200
        assert response.json().get("username") == "testuser2"

        # Test not existed user
        response = client.get(
            "/user/testuser3",
            headers={"Authorization": "Bearer 1"},
        )
        
        assert response.status_code == 404

    def test_updateBio(self, client):
        # Test normal
        response = client.put(
            "/user/bio",
            headers={"Authorization": "Bearer 1"},
            data={"bio": "Test bio"}
        )
        assert response.status_code == 200
        
        # Test invalid
        response = client.put(
            "/user/bio",
            headers={"Authorization": "Bearer 1"},
            data={"bio": ""}
        )
        assert response.status_code == 422

    def test_updateUsername(self, client):
        # Test normal
        response = client.put(
            "/user/username",
            headers={"Authorization": "Bearer 2"},
            data={"username": "newtestuser2"}
        )
        assert response.status_code == 200
        
        # Test invalid
        response = client.put(
            "/user/username",
            headers={"Authorization": "Bearer 2"},
            data={"username": ""}
        )
        assert response.status_code == 422
        
        # Test duplicate
        response = client.put(
            "/user/username",
            headers={"Authorization": "Bearer 2"},
            data={"username": "testuser1"}
        )
        assert response.status_code == 409

    def test_updateEmail(self, client, monkeypatch, mock_db):
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)

        # Test duplicate
        response = client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "email2@example.com"}
        )
        assert response.status_code == 409
        
        # Test invalid
        response = client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "asdf"}
        )
        assert response.status_code == 422
        
        # Test not existed email
        response = client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "abcd@example.com"}
        )
        assert response.status_code == 500
        
        # Test normal
        response = client.put(
            "/user/email",
            headers={"Authorization": "Bearer 1"},
            data={"email": "newemail1@example.com"}
        )
        assert response.status_code == 200

        # Test wrong otp
        r = client.post(
            "/user/email/confirm",
            headers={"Authorization": "Bearer 1"},
            data={"otp": "000000"}
        )
        assert r.status_code == 401

        otp = mock_db.query(OTP).filter(OTP.username == "testuser1", OTP.purpose == OTP_Purpose.OTP_EMAIL_CHANGE, OTP.is_token_used == False).first()
        
        # Test correct
        r = client.post(
            "/user/email/confirm",
            headers={"Authorization": "Bearer 1"},
            data={"otp": otp.otp_code}
        )
        assert r.status_code == 200
        assert mock_db.query(User).filter(User.username == "testuser1").first().email == "newemail1@example.com"

    def test_updatePassword(self, client):
        # Test wrong password
        r = client.put(
            "/user/password",
            headers={"Authorization": "Bearer 1"},
            data={
                "password": "testuser1passwd",
                "new_password": "Tedskwke"
            }
        )
        assert r.status_code == 401

        # Test new password invalid
        r = client.put(
            "/user/password",
            headers={"Authorization": "Bearer 1"},
            data={
                "password": "testuser1passwd",
                "new_password": "Twke"
            }
        )
        assert r.status_code == 422

        # Test normal
        r = client.put(
            "/user/password",
            headers={"Authorization": "Bearer 1"},
            data={
                "password": "testuser1password",
                "new_password": "newtestuser1password"
            }
        )
        assert r.status_code == 200

    def test_cancelEmailChange(self, client, monkeypatch):
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)

        response = client.put(
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
        r = client.get("/cancel/emailchange/" + wrongtoken)
        assert r.status_code == 400

        # Test correct token
        r = client.get("/cancel/emailchange/" + token)
        assert r.status_code == 200

        # Test used token
        r = client.get("/cancel/emailchange/" + token)
        assert r.status_code == 400

# db.close()