from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import get_settings

settings = get_settings()
engine = create_engine(str(settings.database.url))
SessionLocal = sessionmaker(bind=engine)
