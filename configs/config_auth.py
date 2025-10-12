from dotenv import load_dotenv
import os

load_dotenv()

# Encryption Constant Enums
class Encryption:
    SECRET_ACCESS_KEY = os.getenv("SECRET_ACCESS_KEY")
    SECRET_REFRESH_KEY = os.getenv("SECRET_REFRESH_KEY")
    SECRET_RESET_KEY = os.getenv("SECRET_RESET_KEY")
    ALGORITHM = os.getenv("ALGORITHM")
    HASH_ALGORITHM = os.getenv("HASH_ALGORITHM")

# Token Duration Enums
class Duration:
    ACCESS_TOKEN_EXPIRE_MINUTES = 15
    REFRESH_TOKEN_EXPIRE_DAYS = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 5
    OTP_EXPIRE_MINUTES = 5
    OTP_MAX_TRIALS = 5
    OTP_RESEND_INTERVAL_MINUTES = 1

# OTP Purpose Enums
class OTP_Purpose:
    OTP_PASSWORD_RESET = "password_reset"
    OTP_LOGIN = "login"
    OTP_EMAIL_CHANGE = "email_change"
    OTP_REGISTER = "register"

class LoginStatus:
    INCORRECT_USERNAME = 'Incorrect username'
    INCORRECT_PASSWORD = 'Incorrect password'
    SUCCESSFUL = ''