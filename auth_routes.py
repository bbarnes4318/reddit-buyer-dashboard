from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta
import json
import httpx
from starlette.middleware.sessions import SessionMiddleware
from urllib.parse import urlencode

import models
from database import get_db
import auth
from auth import get_current_active_user

router = APIRouter(prefix="/auth", tags=["authentication"])
templates = Jinja2Templates(directory="templates")

# Login page
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

# Sign up page
@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse("signup.html", {"request": request, "error": error})

# Email/password login
@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Incorrect username or password"}
        )
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # Set token in session cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True,
        secure=True,  # For HTTPS
        samesite="lax",  # Allow redirects
        path="/",  # Available across the entire site
        max_age=86400 * 30  # 30 days
    )
    
    # Also store in the session for redundancy
    request.session["access_token"] = f"Bearer {access_token}"
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    
    return response

# Sign up with email
@router.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if email already exists
    db_user = auth.get_user_by_email(db, email)
    if db_user:
        return templates.TemplateResponse(
            "signup.html", 
            {"request": request, "error": "Email already registered"}
        )
    
    # Check if username already exists
    db_user = auth.get_user_by_username(db, username)
    if db_user:
        return templates.TemplateResponse(
            "signup.html", 
            {"request": request, "error": "Username already taken"}
        )
    
    # Create user
    user = auth.create_user(db, email, username, password)
    
    # Create access token
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # Set token in session cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True,
        secure=True,  # For HTTPS
        samesite="lax",  # Allow redirects
        path="/",  # Available across the entire site
        max_age=86400 * 30  # 30 days
    )
    
    # Also store in the session for redundancy
    request.session["access_token"] = f"Bearer {access_token}"
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    
    return response

# Google OAuth login
@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await auth.oauth.google.authorize_redirect(request, redirect_uri)

# Google OAuth callback
@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await auth.oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    
    if not user_info:
        return RedirectResponse(url="/auth/login?error=Failed+to+get+user+info")
    
    # Check if user exists by Google ID
    email = user_info.get("email")
    google_id = user_info.get("sub")
    
    db_user = db.query(models.User).filter(
        models.User.auth_provider == "google",
        models.User.auth_provider_id == google_id
    ).first()
    
    if not db_user:
        # Check if email exists but with different auth provider
        db_user_email = auth.get_user_by_email(db, email)
        
        if db_user_email:
            # Link Google auth to existing account
            db_user_email.auth_provider = "google"
            db_user_email.auth_provider_id = google_id
            db.commit()
            db_user = db_user_email
        else:
            # Create new user with Google auth
            username = f"google_{google_id[:8]}"
            index = 1
            
            # Make sure username is unique
            while auth.get_user_by_username(db, username):
                username = f"google_{google_id[:8]}_{index}"
                index += 1
                
            db_user = auth.create_user(
                db, 
                email=email, 
                username=username, 
                auth_provider="google", 
                auth_provider_id=google_id
            )
    
    # Create access token
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    
    # Set token in session cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    
    # Explicitly set a domain-less cookie to work in all environments
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True,
        secure=True,  # For HTTPS
        samesite="lax",  # Allow redirects
        path="/",  # Available across the entire site
        max_age=86400 * 30  # 30 days
    )
    
    # Also store in the session for redundancy
    request.session["access_token"] = f"Bearer {access_token}"
    request.session["user_id"] = db_user.id
    request.session["username"] = db_user.username
    
    print(f"Login successful for {db_user.username} - Token set in cookies and session")
    
    return response

# Reddit OAuth login
@router.get("/reddit/login")
async def reddit_login(request: Request):
    # Set a unique state for CSRF protection
    request.session["oauth_state"] = auth.generate_state()
    redirect_uri = request.url_for("reddit_callback")
    
    return await auth.oauth.reddit.authorize_redirect(
        request, 
        redirect_uri,
        state=request.session["oauth_state"],
        duration="permanent",
        scope="identity read history"
    )

# Reddit OAuth callback
@router.get("/reddit/callback")
async def reddit_callback(request: Request, db: Session = Depends(get_db)):
    # Verify state to prevent CSRF
    if request.query_params.get("state") != request.session.get("oauth_state"):
        return RedirectResponse(url="/auth/login?error=Invalid+state+parameter")
    
    token = await auth.oauth.reddit.authorize_access_token(request)
    
    # Get Reddit user info
    headers = {
        "Authorization": f"Bearer {token.get('access_token')}",
        "User-Agent": "RedditBuyerIntentDashboard/1.0"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get("https://oauth.reddit.com/api/v1/me", headers=headers)
        
    if response.status_code != 200:
        return RedirectResponse(url="/auth/login?error=Failed+to+get+Reddit+user+info")
        
    user_info = response.json()
    
    # Check if user exists by Reddit ID
    reddit_id = user_info.get("id")
    reddit_username = user_info.get("name")
    
    db_user = db.query(models.User).filter(
        models.User.auth_provider == "reddit",
        models.User.auth_provider_id == reddit_id
    ).first()
    
    if not db_user:
        # Create new user with Reddit auth
        username = f"reddit_{reddit_username}"
        index = 1
        
        # Make sure username is unique
        while auth.get_user_by_username(db, username):
            username = f"reddit_{reddit_username}_{index}"
            index += 1
            
        db_user = auth.create_user(
            db, 
            email=f"{reddit_username}@reddit.com",  # Reddit doesn't provide email
            username=username, 
            auth_provider="reddit", 
            auth_provider_id=reddit_id
        )
    
    # Create or update a Reddit account for this user
    existing_account = db.query(models.RedditAccount).filter(
        models.RedditAccount.owner_id == db_user.id,
        models.RedditAccount.username == reddit_username
    ).first()
    
    # Current time for token expiration calculation
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=token.get('expires_in', 3600))
    
    if existing_account:
        # Update existing account with new tokens
        existing_account.access_token = token.get('access_token')
        existing_account.refresh_token = token.get('refresh_token')
        existing_account.token_expires_at = expires_at
        existing_account.last_used = now
        db.commit()
    else:
        # Create new Reddit account
        new_account = models.RedditAccount(
            username=reddit_username,
            access_token=token.get('access_token'),
            refresh_token=token.get('refresh_token'),
            token_expires_at=expires_at,
            owner_id=db_user.id,
            created_at=now,
            last_used=now
        )
        db.add(new_account)
        db.commit()
    
    # Create access token for our app
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    
    # Set token in session cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True,
        secure=True,  # For HTTPS
        samesite="lax",  # Allow redirects
        path="/",  # Available across the entire site
        max_age=86400 * 30  # 30 days
    )
    
    # Also store in the session for redundancy
    request.session["access_token"] = f"Bearer {access_token}"
    request.session["user_id"] = db_user.id
    request.session["username"] = db_user.username
    
    return response

# Connect Reddit account (for already logged-in users)
@router.get("/reddit/connect")
async def connect_reddit_account(
    request: Request,
    current_user: models.User = Depends(get_current_active_user)
):
    # Set a unique state for CSRF protection
    request.session["oauth_state"] = auth.generate_state()
    redirect_uri = request.url_for("reddit_connect_callback")
    
    # Store current user ID in session to identify the user on callback
    request.session["connecting_user_id"] = current_user.id
    
    return await auth.oauth.reddit.authorize_redirect(
        request, 
        redirect_uri,
        state=request.session["oauth_state"],
        duration="permanent",
        scope="identity read history"
    )

# Reddit connect callback (for already logged-in users)
@router.get("/reddit/connect/callback")
async def reddit_connect_callback(request: Request, db: Session = Depends(get_db)):
    # Verify state to prevent CSRF
    if request.query_params.get("state") != request.session.get("oauth_state"):
        return RedirectResponse(url="/account?error=Invalid+state+parameter")
    
    # Get user ID from session
    user_id = request.session.get("connecting_user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login?error=Session+expired")
    
    # Verify user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        return RedirectResponse(url="/auth/login?error=User+not+found")
    
    token = await auth.oauth.reddit.authorize_access_token(request)
    
    # Get Reddit user info
    headers = {
        "Authorization": f"Bearer {token.get('access_token')}",
        "User-Agent": "RedditBuyerIntentDashboard/1.0"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get("https://oauth.reddit.com/api/v1/me", headers=headers)
        
    if response.status_code != 200:
        return RedirectResponse(url="/account?error=Failed+to+get+Reddit+user+info")
        
    user_info = response.json()
    reddit_username = user_info.get("name")
    
    # Check if this account already exists for this user
    existing_account = db.query(models.RedditAccount).filter(
        models.RedditAccount.owner_id == user_id,
        models.RedditAccount.username == reddit_username
    ).first()
    
    # Current time for token expiration calculation
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=token.get('expires_in', 3600))
    
    if existing_account:
        # Update existing account with new tokens
        existing_account.access_token = token.get('access_token')
        existing_account.refresh_token = token.get('refresh_token')
        existing_account.token_expires_at = expires_at
        existing_account.last_used = now
        db.commit()
        
        success_message = f"Reddit account u/{reddit_username} reconnected successfully"
    else:
        # Create new Reddit account
        new_account = models.RedditAccount(
            username=reddit_username,
            access_token=token.get('access_token'),
            refresh_token=token.get('refresh_token'),
            token_expires_at=expires_at,
            owner_id=user_id,
            created_at=now,
            last_used=now
        )
        db.add(new_account)
        db.commit()
        
        success_message = f"Reddit account u/{reddit_username} connected successfully"
    
    # Clear session variables
    if "oauth_state" in request.session:
        del request.session["oauth_state"]
    if "connecting_user_id" in request.session:
        del request.session["connecting_user_id"]
    
    # Redirect to account page with success message
    return RedirectResponse(
        url=f"/account?success={success_message}",
        status_code=status.HTTP_302_FOUND
    )

# Logout
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login")
    response.delete_cookie("access_token")
    return response 