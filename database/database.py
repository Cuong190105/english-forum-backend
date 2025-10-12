from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from fastapi import Depends
from typing import Annotated
from configs.config_db import *

DB_URL = DB_CONNECTION + '+' + DB_DRIVER + '://'\
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