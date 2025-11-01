from typing import Literal
from dotenv import load_dotenv
import os

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "development")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")
FilePurpose = Literal['avatar', 'attachment']