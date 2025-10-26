from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from fastapi import Depends
from typing import Annotated
from configs.config_db import *
import os

def createConnection():
    try:
        DB_URL = DB_CONNECTION + '+' + DB_DRIVER + '://'\
            + DB_USERNAME + ':' + DB_PASSWORD\
            + '@' + DB_HOST + ':' + DB_PORT\
            + '/' + DB_DATABASE

        ssl = {
            "ssl_ca": os.path.abspath("certs/DigiCertGlobalRootG2.crt.pem")
        }

        engine = create_engine(DB_URL, connect_args=ssl)
        return engine
    except:
        return None

engine = createConnection()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def create_db_and_tables(drop: bool = False):
    # Clear all database in dev env
    if drop:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

Db_dependency = Annotated[Session, Depends(get_db)]