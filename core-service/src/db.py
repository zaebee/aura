import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, Float, String, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker

from config import get_settings

settings = get_settings()

Base = declarative_base()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    base_price = Column(Float, nullable=False)
    floor_price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    meta = Column(JSONB, default={})
    embedding = Column(Vector(1024))


def init_db():
    Base.metadata.create_all(bind=engine)
