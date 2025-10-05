from dotenv import load_dotenv
import os

load_dotenv()

DB_CONNECTION = os.getenv("DB_CONNECTION", "mysql")
DB_USERNAME = os.getenv("DB_USERNAME", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_DATABASE = os.getenv("DB_DATABASE", "english_forum")