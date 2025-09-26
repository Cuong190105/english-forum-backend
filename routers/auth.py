from fastapi import APIRouter, Form, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from pydantic import BaseModel
from database.database import Db_dependency
from database import models
import bcrypt
from datetime import datetime, timedelta
from typing import Annotated
from config import SECRET_ACCESS_KEY, SECRET_REFRESH_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: int | None = None
    exp: datetime | None = None

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def createToken(data: dict, expires_delta: timedelta = ACCESS_TOKEN_EXPIRE_MINUTES, secret_key: str = SECRET_ACCESS_KEY):
    """Generate a JWT token."""

    # Copy data to avoid modifying the original dictionary
    # to_encode: dict using TokenData model
    to_encode = data.copy()
    expire = datetime.now(datetime.timezone.utc) + expires_delta
    to_encode.update({"exp": expire})

    # Generate the JWT token
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def validateToken(token: str, secret_key: str):
    """
    Check if the token is valid and not expired.\n
    Return token payload on success.\n
    Raise HTTPException if invalid or expired.
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        exp = payload.get("exp")
        if exp is None or datetime.fromtimestamp(exp) < datetime.now(datetime.timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        return payload
    except jwt.exceptions.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

async def validateRefreshToken(token: str, db: Db_dependency):
    pass

async def getUserFromToken(token: Annotated[str, Depends(oauth2_scheme)], db: Db_dependency):
    """
    Get the current user from the JWT token.
    """
    
    # Decode the JWT token and extract the user ID
    payload = validateToken(token, SECRET_ACCESS_KEY)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    # Fetch the user from the database
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

async def getUserIdByUsername(username: str, db: Db_dependency):
    """
    Get user ID by username.\n
    Returns user ID if found, else -1.
    """
    user = db.query(models.User).filter(models.User.username == username).first()
    if user:
        return user.user_id
    return -1

async def getUserIdByEmail(email: str, db: Db_dependency):
    """
    Get user ID by email address.\n
    Returns user ID if found, else -1.
    """
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        return user.user_id
    return -1

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(request: Annotated[OAuth2PasswordRequestForm, Depends()], db: Db_dependency):
    """
    Handle login requests.
    Request form must include:
    - username: str (can be username or email)
    - password: str

    On success, returns an access token.\n
    On failure, raises HTTPException with appropriate status code and detail.
    """

    # Check if user exists by username or email
    user_id = await getUserIdByUsername(request.username, db)
    if user_id == -1:
        user_id = await getUserIdByEmail(request.username, db)
    if user_id == -1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Verify password
    credentials = db.query(models.Credentials).filter(models.Credentials.user_id == user_id).first()
    isCorrectPassword = bcrypt.checkpw(request.password.encode('utf-8'), credentials.password_hash.encode('utf-8'))
    if isCorrectPassword == False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    # Create and return access token
    access_token = createToken(
        data={"sub": user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        secret_key=SECRET_ACCESS_KEY
    )
    refresh_token = createToken(
        data={"sub": user_id},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        secret_key=SECRET_REFRESH_KEY
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: Db_dependency):
    """
    Handle user registration requests.
    Request body must include:
    - username: str
    - password: str
    - email: str
    On success, 
    """

    # Check if username or email already exists
    user_id = await getUserIdByUsername(request.username, db)
    if user_id != -1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    
    user_id = await getUserIdByEmail(request.email, db)
    if user_id != -1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
    
    # Hash the password
    salt = bcrypt.gensalt()
    pwhash = bcrypt.hashpw(request.password.encode('utf-8'), salt)
    
    # Create new user and credentials
    new_user = models.User(
        username=request.username,
        email=request.email,
        bio=None,
        avatar_url=None,
        email_verified_at=None,
        created_at=None,
        updated_at=None
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    new_credentials = models.Credentials(
        user_id=new_user.user_id,
        password_hash=pwhash,
        hash_algorithm='bcrypt'
    )
    db.add(new_credentials)
    db.commit()
    
    # Automatically log in the user after registration
    access_token = await login(OAuth2PasswordRequestForm(username=request.username, password=request.password, scope=""), db)

    return access_token

@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refreshToken(current_user: Annotated[models.User, Depends(getUserFromToken)]):
    access_token = createToken(
        data={"sub": current_user.user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        secret_key=SECRET_ACCESS_KEY
    )
    return Token(access_token=access_token, token_type="bearer")

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(access_token: Annotated[str, Depends(oauth2_scheme)], refresh_token: Annotated[str, Depends(oauth2_scheme)]):
    """Handle user logout by invalidating tokens."""
    access_payload = validateToken(access_token, SECRET_ACCESS_KEY)
    refresh_payload = validateToken(refresh_token, SECRET_REFRESH_KEY)

@router.post("/recover")
async def recoverPassword(username: str):
    if getUserIdByUsername(username) != -1 or getUserIdByEmail(username) != -1:
        return {"message": "Recovery email sent"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

@router.post("/recover/verify")
async def verifyRecoveryToken(token: str):
    if token == "valid_token":
        return {"message": "Token is valid"}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

@router.post("/reset")
async def resetPassword(token: str, new_password: str, db: Db_dependency):
    if token != "valid_token":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    
    user_id = 1  # This should be extracted from the token in a real implementation
    credentials = db.query(models.Credentials).filter(models.Credentials.user_id == user_id).first()
    if not credentials:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User credentials not found")
    
    salt = bcrypt.gensalt()
    pwhash = bcrypt.hashpw(new_password.encode('utf-8'), salt)
    
    credentials.password_hash = pwhash
    db.commit()
    
    return {"message": "Password reset successful"}