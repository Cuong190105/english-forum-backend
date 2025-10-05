from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from fastapi import Depends
from typing import Annotated
from configs.config_db import *
if 'DB_CONNECTION' in globals() and DB_CONNECTION == 'sqlite':
    DB_URL = f"sqlite:///{DB_DATABASE}"
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
else:
    # default: use MySQL via PyMySQL
    DB_URL = 'mysql+pymysql://'\
        + DB_USERNAME + ':' + DB_PASSWORD\
        + '@' + DB_HOST + ':' + DB_PORT\
        + '/' + DB_DATABASE
    engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

Db_dependency = Annotated[Session, Depends(get_db)]