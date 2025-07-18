import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ARRAY, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from datetime import datetime

DB_URL = os.environ.get('POSTGRES_URL', 'postgresql://tvidz:tvidz@postgres:5432/tvidz')
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Video(Base):
    __tablename__ = 'videos'
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    thumbnail_path = Column(String)
    duplicates = Column(PG_ARRAY(Integer), default=list)
    # Relationship
    timestamps = relationship('VideoTimestamps', back_populates='video', uselist=False)

class VideoTimestamps(Base):
    __tablename__ = 'video_timestamps'
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'))
    timestamps = Column(PG_ARRAY(Float), nullable=False)
    video = relationship('Video', back_populates='timestamps')

# Create tables
Base.metadata.create_all(engine)

def add_video(filename, thumbnail_path=None):
    session = SessionLocal()
    try:
        video = Video(filename=filename, thumbnail_path=thumbnail_path)
        session.add(video)
        session.commit()
        session.refresh(video)
        return video
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def add_timestamps(video_id, timestamps):
    session = SessionLocal()
    try:
        # Check if timestamps already exist for this video
        existing = session.query(VideoTimestamps).filter_by(video_id=video_id).first()
        if existing:
            # Update existing timestamps
            existing.timestamps = timestamps
        else:
            # Create new timestamps record
            ts = VideoTimestamps(video_id=video_id, timestamps=timestamps)
            session.add(ts)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def update_duplicates(video_id, duplicate_ids):
    session = SessionLocal()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if video:
            video.duplicates = duplicate_ids
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def find_duplicates(new_timestamps, min_match=3):
    """
    Returns a list of (video_id, match_count) for videos whose timestamps contain at least min_match elements of new_timestamps.
    Optimized version using set intersections for better performance.
    """
    session = SessionLocal()
    try:
        candidates = session.query(VideoTimestamps).all()
        results = []
        new_timestamps_set = set(new_timestamps)
        for cand in candidates:
            # Count how many timestamps match using set intersection (more efficient)
            match_count = len(set(cand.timestamps) & new_timestamps_set)
            if match_count >= min_match:
                results.append((cand.video_id, match_count))
        return results
    finally:
        session.close()

def get_video_by_id(video_id):
    session = SessionLocal()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        return video
    finally:
        session.close()

def get_video_by_filename(filename):
    session = SessionLocal()
    try:
        video = session.query(Video).filter_by(filename=filename).first()
        return video
    finally:
        session.close() 