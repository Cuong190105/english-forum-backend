import pytest
from database.models import OTP, User, Credentials
from configs.config_auth import OTP_Purpose

async def mock_send_email(subject: str, content: str, target: str):
    corrent_email = ["email1@example.com", "email2@example.com", "email3@example.com", "email4@example.com"]
    if target not in corrent_email:
        raise Exception("Failed to send email to " + target)

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestAuth:

    @pytest.mark.usefixtures("check")
    def test_login(self, client):
        response = client.post(
            "/login",
            data={
                "username": "testuser1",
                "password": "testuser1password",
            })
        
        assert response.status_code == 200
        assert "access_token" in response.json()

        # Test not existed username
        response = client.post(
            "/login",
            data={
                "username": "randomuser",
                "password": "testuser1password",
            })
        
        assert response.status_code == 404

        # Test wrong password
        response = client.post(
            "/login",
            data={
                "username": "testuser1",
                "password": "wrongpassword",
            })
        
        assert response.status_code == 406

    @pytest.mark.usefixtures("check")
    def test_register(self, client, monkeypatch):
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)
        response = client.post(
            "/register",
            data={
                "username": "testuser3",
                "password": "testuser3password",
                "email": "email3@example.com"
            })
        
        assert response.status_code == 201
        assert "access_token" in response.json()

        # Test duplicate username
        response = client.post(
            "/register",
            data={
                "username": "testuser1",
                "password": "testuser4password",
                "email": "email4@example.com"
            })
        
        assert response.status_code == 400

        # Test duplicate email
        response = client.post(
            "/register",
            data={
                "username": "testuser4",
                "password": "testuser4password",
                "email": "email1@example.com"
            })
        assert response.status_code == 400

        # Test invalid email
        response = client.post(
            "/register",
            data={
                "username": "testuser4",
                "password": "testuser4password",
                "email": "invalidemail"
            })
        assert response.status_code == 422

        # Test email sending failure
        response = client.post(
            "/register",
            data={
                "username": "testuser4",
                "password": "testuser4password",
                "email": "email999@gmail.com",
            })
        assert response.status_code == 500

    @pytest.mark.usefixtures("check")
    def test_verify_account(self, client, monkeypatch, mock_db):
        otp = mock_db.query(OTP).filter(OTP.username == "testuser3").first()
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)
        # Test wrong code
        wrong_response = client.post(
            "/register/verify",
            headers = {"Authorization": f"Bearer 3"},
            data={
                "otp": '000000',
            })
        assert wrong_response.status_code == 400
        assert wrong_response.json().get("detail") == "Invalid OTP"

        # Test invalid code
        wrong_response = client.post(
            "/register/verify",
            headers = {"Authorization": f"Bearer 3"},
            data={
                "otp": '00000',
            })
        assert wrong_response.status_code == 422

        wrong_response = client.post(
            "/register/verify",
            headers = {"Authorization": f"Bearer 3"},
            data={
                "otp": '0000000',
            })
        assert wrong_response.status_code == 422

        # Test correct code
        response = client.post(
            "/register/verify",
            headers = {"Authorization": f"Bearer 3"},
            data={
                "otp": otp.otp_code,
            })
        assert response.status_code == 200

        # Test already verified
        wrong_response = client.post(
            "/register/verify",
            headers = {"Authorization": f"Bearer 3"},
            data={
                "otp": otp.otp_code,
            })
        assert wrong_response.json().get("detail") == "Email verified before"

    @pytest.mark.usefixtures("check")
    def test_resend(self, client, monkeypatch, mock_db):
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)
        user = mock_db.query(User).filter(User.user_id == 1).first()
        user.email_verified_at = None
        # Test send normal
        r = client.post(
            "/register/resend",
            headers = {"Authorization": f"Bearer 1"}
        )
        assert r.status_code == 200

        # Test send too fast
        r = client.post(
            "/register/resend",
            headers = {"Authorization": f"Bearer 1"}
        )
        assert r.status_code == 429

        # Test already verified
        r = client.post(
            "/register/resend",
            headers = {"Authorization": f"Bearer 3"}
        )
        assert r.status_code == 400

    @pytest.mark.usefixtures("check")
    def test_refresh(self, client):
        r = client.post(
            "/login",
            data = {
                "username": "testuser1",
                "password": "testuser1password",
            }
        )
        rft = r.json().get("refresh_token")

        # Test correct token
        r = client.post(
            "/refresh",
            data = {
                "refresh_token": rft
            }
        )
        assert r.status_code == 200
        assert r.json().get("access_token") is not None

        # Test invalid token
        r = client.post(
            "/refresh",
            data = {
                "refresh_token": "7T8MPw03lnFQzf4T0j4uHPZYvyNpNxdZHU2HMh3gfI0GIBH+63FtkJ0QZD8hsTwq"
            }
        )
        assert r.status_code == 401

    @pytest.mark.usefixtures("check")
    def test_logout(self, client):
        r = client.post(
            "/login",
            data = {
                "username": "testuser1",
                "password": "testuser1password",
            }
        )
        acs = r.json().get("access_token")

        # Test invalid token
        r = client.post(
            "/logout",
            headers={"Authorization": "Bearer 7T8MPw03lnFQzf4T0j4uHPZYvyNpNxdZHU2HMh3gfI0GIBH+63FtkJ0QZD8hsTwq"}
        )
        assert r.status_code == 400

        # Test valid token
        r = client.post(
            "/logout",
            headers={"Authorization": f"Bearer {acs}"}
        )
        assert r.status_code == 200

    @pytest.mark.usefixtures("check")
    def test_recover_password(self, client, monkeypatch):
        monkeypatch.setattr("utilities.mailer.send", mock_send_email)

        # Test normal request
        r = client.post(
            "/recover",
            data = {
                "username": "testuser1",
            }
        )
        assert r.status_code == 200
        
        # Test request too fast
        r = client.post(
            "/recover",
            data = {
                "username": "testuser1",
            }
        )
        assert r.status_code == 429
        
        # Test user not found
        r = client.post(
            "/recover",
            data = {
                "username": "testuser999",
            }
        )
        assert r.status_code == 404

    @pytest.mark.usefixtures("check")
    def test_recoverVerify_andReset(self, client, mock_db):
        otp = mock_db.query(OTP).filter(OTP.username == "testuser1", OTP.purpose == OTP_Purpose.OTP_PASSWORD_RESET).first()
        # Test invalid username
        r = client.post(
            "/recover/verify",
            data = {
                "username": "testuser2",
                "otp": otp.otp_code,
            }
        )
        assert r.status_code == 400

        # Test invalid otp
        r = client.post(
            "/recover/verify",
            data = {
                "username": "testuser1",
                "otp": "000000"
            }
        )
        assert r.status_code == 400
        r = client.post(
            "/recover/verify",
            data = {
                "username": "testuser1",
                "otp": "00000"
            }
        )
        assert r.status_code == 422

        # Test valid otp
        r = client.post(
            "/recover/verify",
            data = {
                "username": "testuser1",
                "otp": otp.otp_code
            }
        )
        assert r.status_code == 200
        rst = r.json().get("reset_token")
        assert rst is not None

        # Test invalid reset token
        r = client.post(
            "/reset",
            data = {
                "reset_token": "7T8MPw03lnFQzf4T0j4uHPZYvyNpNxdZHU2HMh3gfI0GIBH+63FtkJ0QZD8hsTwq",
                "new_password": "testuser1newpassword"
            }
        )
        assert r.status_code == 401

        # Test invalid password
        r = client.post(
            "/reset",
            data = {
                "reset_token": rst,
                "new_password": "test"
            }
        )
        assert r.status_code == 422

        # Test valid reset token
        r = client.post(
            "/reset",
            data = {
                "reset_token": rst,
                "new_password": "testuser1newpassword"
            }
        )
        assert r.status_code == 200