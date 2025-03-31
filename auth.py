from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
import secrets
import logging

import models
from database import get_db
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Generate a secure state token for CSRF protection
def generate_state():
    return secrets.token_urlsafe(32)

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth setup
config = Config(environ=os.environ)
oauth = OAuth(config)

# Google OAuth
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# Reddit OAuth
oauth.register(
    name="reddit",
    client_id=os.getenv("REDDIT_OAUTH_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_OAUTH_CLIENT_SECRET"),
    authorize_url="https://www.reddit.com/api/v1/authorize",
    access_token_url="https://www.reddit.com/api/v1/access_token",
    client_kwargs={"scope": "identity read"},
)

# OAuth2 password bearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# User functions
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, email: str, username: str, password: Optional[str] = None, 
                auth_provider: str = "email", auth_provider_id: Optional[str] = None):
    hashed_password = get_password_hash(password) if password else None
    
    db_user = models.User(
        email=email,
        username=username,
        hashed_password=hashed_password,
        auth_provider=auth_provider,
        auth_provider_id=auth_provider_id
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    
    if not user:
        return False
        
    if not user.hashed_password:
        return False
        
    if not verify_password(password, user.hashed_password):
        return False
        
    return user

# Token validation
async def get_current_user(token: str = Depends(oauth2_scheme), request: Request = None, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # If token is not provided via Authorization header, try to get it from session
    if not token and request:
        session_token = request.session.get("access_token")
        if session_token and session_token.startswith("Bearer "):
            token = session_token.replace("Bearer ", "")
    
    if not token:
        raise credentials_exception
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username is None:
            raise credentials_exception
            
    except JWTError as e:
        logger.error(f"JWT Error: {str(e)}")
        raise credentials_exception
        
    user = get_user_by_username(db, username)
    
    if user is None:
        raise credentials_exception
        
    return user

# Get current active user
async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return current_user

# Reddit account functions
def get_reddit_accounts(db: Session, user_id: int):
    return db.query(models.RedditAccount).filter(models.RedditAccount.owner_id == user_id).all()

def create_reddit_account(db: Session, user_id: int, username: str, client_id: str, 
                         client_secret: str, password: str, user_agent: str):
    db_account = models.RedditAccount(
        username=username,
        client_id=client_id,
        client_secret=client_secret,
        password=password,
        user_agent=user_agent,
        owner_id=user_id
    )
    
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

def update_reddit_account(db: Session, account_id: int, user_id: int, **kwargs):
    db_account = db.query(models.RedditAccount).filter(
        models.RedditAccount.id == account_id,
        models.RedditAccount.owner_id == user_id
    ).first()
    
    if not db_account:
        return None
        
    for key, value in kwargs.items():
        setattr(db_account, key, value)
        
    db.commit()
    db.refresh(db_account)
    return db_account

def delete_reddit_account(db: Session, account_id: int, user_id: int):
    db_account = db.query(models.RedditAccount).filter(
        models.RedditAccount.id == account_id,
        models.RedditAccount.owner_id == user_id
    ).first()
    
    if not db_account:
        return False
        
    db.delete(db_account)
    db.commit()
    return True 