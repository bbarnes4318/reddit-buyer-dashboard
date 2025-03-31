from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)  # Nullable for OAuth users
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    auth_provider = Column(String, default="email")  # email, google, reddit
    auth_provider_id = Column(String, nullable=True)  # ID from the provider

    # Relationship with RedditAccount
    reddit_accounts = relationship("RedditAccount", back_populates="owner", cascade="all, delete-orphan")

class RedditAccount(Base):
    __tablename__ = "reddit_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    
    # OAuth tokens
    access_token = Column(String)
    refresh_token = Column(String)
    token_expires_at = Column(DateTime)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, nullable=True)
    
    # Foreign key to User
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="reddit_accounts")
    
    # Relationship with MonitoringSession
    monitoring_sessions = relationship("MonitoringSession", back_populates="reddit_account", cascade="all, delete-orphan")

class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    subreddits = Column(Text)  # Stored as JSON
    keywords = Column(Text)  # Stored as JSON
    min_intent = Column(String, default="MEDIUM")
    min_confidence = Column(Float, default=0.6)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_run = Column(DateTime, nullable=True)
    
    # Foreign key to RedditAccount
    reddit_account_id = Column(Integer, ForeignKey("reddit_accounts.id"))
    reddit_account = relationship("RedditAccount", back_populates="monitoring_sessions") 