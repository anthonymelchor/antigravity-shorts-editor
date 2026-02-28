from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime

Base = declarative_base()

class SystemStatus(Base):
    __tablename__ = 'system_status'
    id = Column(Integer, primary_key=True)
    service_name = Column(String, unique=True)
    last_heartbeat = Column(DateTime, default=datetime.datetime.utcnow)

class Account(Base):
    """
    Represents a Social Media account (IG/TikTok/YT) to be automated.
    """
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    platform = Column(String, default='instagram')
    niche = Column(String, nullable=False)
    keywords = Column(JSON, nullable=True) # List of search terms
    target_url = Column(String, nullable=True) # Link to sell (Hotmart/TSL)
    
    # Relationships
    discoveries = relationship("DiscoveryResult", back_populates="account")

class DiscoveryResult(Base):
    """
    Videos found by the discovery engine that are candidates for processing.
    """
    __tablename__ = 'discovery_results'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'))
    title = Column(String)
    original_url = Column(String, unique=True, nullable=False)
    platform = Column(String, default='youtube')
    
    # Metrics for velocity calculation
    views = Column(Integer, default=0)
    duration = Column(Integer, default=0) # Duration in seconds
    likes = Column(Integer, default=0)
    uploaded_at = Column(DateTime)
    discovery_score = Column(Float, default=0.0) # AI Viral Score (0-100)
    
    # State tracking
    status = Column(String, default='discovered') # discovered, approved, processing, completed, failed
    content_type = Column(String, default='value') # value, viral, sales
    
    # Metadata
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    account = relationship("Account", back_populates="discoveries")

# Database setup
engine = create_engine('sqlite:///app_database.db', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
