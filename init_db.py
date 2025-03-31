import logging
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from models import Base
from database import engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

def init_db():
    """Initialize the database by creating all tables."""
    try:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

if __name__ == "__main__":
    init_db() 