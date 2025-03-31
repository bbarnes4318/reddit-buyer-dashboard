import logging
import sys
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
import os

from models import Base, User
from database import engine, get_db
from auth import get_password_hash

# Configure logging to use stdout for App Engine compatibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def init_db():
    """Initialize the database by creating all tables."""
    try:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
        
        # Check if we need to create an admin user
        db = next(get_db())
        admin_user = db.query(User).filter(User.email == "admin@example.com").first()
        
        if not admin_user:
            logger.info("Creating admin user...")
            admin_password = os.environ.get("ADMIN_PASSWORD", "admin1234")
            hashed_password = get_password_hash(admin_password)
            
            admin_user = User(
                email="admin@example.com",
                username="admin",
                hashed_password=hashed_password,
                is_active=True,
                auth_provider="email"
            )
            
            db.add(admin_user)
            db.commit()
            logger.info("Admin user created successfully.")
        
    except SQLAlchemyError as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

if __name__ == "__main__":
    init_db() 