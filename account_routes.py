from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import json
from datetime import datetime

import models
from database import get_db
import auth
from auth import get_current_active_user

router = APIRouter(prefix="/account", tags=["account"])
templates = Jinja2Templates(directory="templates")

# Account management page
@router.get("/", response_class=HTMLResponse)
async def account_page(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    error: Optional[str] = None,
    success: Optional[str] = None
):
    # Get user's Reddit accounts
    reddit_accounts = auth.get_reddit_accounts(db, current_user.id)
    
    return templates.TemplateResponse(
        "account.html", 
        {
            "request": request, 
            "user": current_user,
            "reddit_accounts": reddit_accounts,
            "error": error,
            "success": success
        }
    )

# Add Reddit account
@router.post("/reddit/add")
async def add_reddit_account(
    request: Request,
    username: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    password: str = Form(...),
    user_agent: str = Form(...),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Check if account with this username already exists for this user
    existing_account = db.query(models.RedditAccount).filter(
        models.RedditAccount.owner_id == current_user.id,
        models.RedditAccount.username == username
    ).first()
    
    if existing_account:
        return templates.TemplateResponse(
            "account.html",
            {
                "request": request,
                "user": current_user,
                "reddit_accounts": auth.get_reddit_accounts(db, current_user.id),
                "error": f"Account with username '{username}' already exists"
            }
        )
    
    # Test Reddit credentials before saving
    try:
        # Import here to avoid circular imports
        from reddit_scraper import RedditScraper
        
        # Create temporary scraper with these credentials
        test_scraper = RedditScraper(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=user_agent
        )
        
        # Try to fetch user identity to verify credentials
        if not test_scraper.test_connection():
            return templates.TemplateResponse(
                "account.html",
                {
                    "request": request,
                    "user": current_user,
                    "reddit_accounts": auth.get_reddit_accounts(db, current_user.id),
                    "error": "Invalid Reddit credentials. Please check and try again."
                }
            )
    except Exception as e:
        return templates.TemplateResponse(
            "account.html",
            {
                "request": request,
                "user": current_user,
                "reddit_accounts": auth.get_reddit_accounts(db, current_user.id),
                "error": f"Error connecting to Reddit: {str(e)}"
            }
        )
    
    # Create the account
    auth.create_reddit_account(
        db, 
        current_user.id, 
        username, 
        client_id, 
        client_secret, 
        password, 
        user_agent
    )
    
    return RedirectResponse(
        url=f"/account?success=Reddit+account+{username}+added+successfully",
        status_code=303
    )

# Get Reddit account data
@router.get("/reddit/{account_id}/data")
async def get_reddit_account_data(
    account_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    account = db.query(models.RedditAccount).filter(
        models.RedditAccount.id == account_id,
        models.RedditAccount.owner_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Return only non-sensitive data
    return JSONResponse({
        "id": account.id,
        "username": account.username,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "last_used": account.last_used.isoformat() if account.last_used else None,
        "is_active": account.is_active
    })

# Edit Reddit account
@router.post("/reddit/{account_id}/edit")
async def edit_reddit_account(
    account_id: int,
    request: Request,
    username: str = Form(...),
    client_id: str = Form(...),
    client_secret: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    user_agent: str = Form(...),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Get the account
    account = db.query(models.RedditAccount).filter(
        models.RedditAccount.id == account_id,
        models.RedditAccount.owner_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check if username is taken by another account
    if username != account.username:
        existing_account = db.query(models.RedditAccount).filter(
            models.RedditAccount.owner_id == current_user.id,
            models.RedditAccount.username == username,
            models.RedditAccount.id != account_id
        ).first()
        
        if existing_account:
            return templates.TemplateResponse(
                "account.html",
                {
                    "request": request,
                    "user": current_user,
                    "reddit_accounts": auth.get_reddit_accounts(db, current_user.id),
                    "error": f"Account with username '{username}' already exists"
                }
            )
    
    # Prepare update data
    update_data = {
        "username": username,
        "client_id": client_id,
        "user_agent": user_agent
    }
    
    # Only update password and client_secret if provided
    if client_secret:
        update_data["client_secret"] = client_secret
    
    if password:
        update_data["password"] = password
    
    # Update account
    auth.update_reddit_account(db, account_id, current_user.id, **update_data)
    
    return RedirectResponse(
        url=f"/account?success=Reddit+account+{username}+updated+successfully",
        status_code=303
    )

# Delete Reddit account
@router.post("/reddit/{account_id}/delete")
async def delete_reddit_account(
    account_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Delete the account
    if not auth.delete_reddit_account(db, account_id, current_user.id):
        raise HTTPException(status_code=404, detail="Account not found")
    
    return RedirectResponse(
        url="/account?success=Reddit+account+deleted+successfully",
        status_code=303
    ) 