from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./scraper.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ProductDB(Base):
    __tablename__ = "products"

    id           = Column(Integer, primary_key=True, index=True)
    platform     = Column(String, index=True)        # "amazon" | "flipkart"
    product_id   = Column(String, index=True)        # ASIN or Flipkart ID
    title        = Column(Text)
    brand        = Column(String, nullable=True)
    price        = Column(Float, nullable=True)       # offer price
    mrp          = Column(Float, nullable=True)       # original price
    discount     = Column(Float, nullable=True)       # % off
    rating       = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    seller       = Column(String, nullable=True)
    availability = Column(String, nullable=True)
    image_url    = Column(Text, nullable=True)
    product_url  = Column(Text)
    scraped_at   = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PriceHistoryDB(Base):
    __tablename__ = "price_history"

    id          = Column(Integer, primary_key=True, index=True)
    product_id  = Column(Integer, index=True)        # FK to products.id
    price       = Column(Float)
    recorded_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
