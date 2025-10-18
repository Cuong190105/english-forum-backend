from configs.config_auth import Encryption
from database.database import Db_dependency
from database.models import User
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from utilities.security import validateToken

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login", refreshUrl="/refresh")

async def getUserFromToken(token: Annotated[str, Depends(oauth2_scheme)], db: Db_dependency, request: Request):
    """
    Get the current user from the JWT token.

    Params:
        token: JWT string
        db: Database session object
        request: Request info. Defaults to the endpoint requests.

    Returns:
        Optional[models.User]: user info.
    """
    # Decode the JWT token and extract the user ID
    payload = validateToken(token, Encryption.SECRET_ACCESS_KEY)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    # Fetch the user from the database
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized")
    
    path = request.scope.get("route").path
    if user.email_verified_at is None and not path.startswith("/register/"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You have to verify your email before using the app")
    return user


User_auth = Annotated[User, Depends(getUserFromToken)]