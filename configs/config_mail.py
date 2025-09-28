from dotenv import load_dotenv
import os

load_dotenv()

# MAIL_MAILER=os.getenv("MAIL_MAILER")
MAIL_HOST=os.getenv("MAIL_HOST")
MAIL_PORT=os.getenv("MAIL_PORT")
MAIL_USERNAME=os.getenv("MAIL_USERNAME")
MAIL_PASSWORD=os.getenv("MAIL_PASSWORD")
MAIL_FROM_ADDRESS=os.getenv("MAIL_FROM_ADDRESS")
MAIL_FROM_NAME=os.getenv("MAIL_FROM_NAME")