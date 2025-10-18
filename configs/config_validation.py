# Username must have between 8 and 50 characters. Only letters in any case, numbers, underscore (_) and period (.) are allowed. First character must be a letter
class Pattern:
    USERNAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_.]+{7, 49}$"
    PASSWORD_PATTERN = r"^.{8, 60}$"
    OTP_PATTERN = r"^[0-9]{6}$"

