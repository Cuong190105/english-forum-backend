from typing import Literal
from dotenv import load_dotenv
import os

load_dotenv()

APP_ENV = os.getenv("APP_ENV")
APP_URL = os.getenv("APP_URL")
FilePurpose = Literal['avatar', 'attachment']