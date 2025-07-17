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
    video = Video(filename=filename, thumbnail_path=thumbnail_path)
    session.add(video)
    session.commit()
    session.refresh(video)
    session.close()
    return video

def add_timestamps(video_id, timestamps):
    session = SessionLocal()
    ts = VideoTimestamps(video_id=video_id, timestamps=timestamps)
    session.add(ts)
    session.commit()
    session.close()

def update_duplicates(video_id, duplicate_ids):
    session = SessionLocal()
    video = session.query(Video).filter_by(id=video_id).first()
    if video:
        video.duplicates = duplicate_ids
        session.commit()
    session.close()

def find_duplicates(new_timestamps, min_match=3):
    """
    Returns a list of (video_id, match_count) for videos whose timestamps contain at least min_match elements of new_timestamps.
    """
    session = SessionLocal()
    candidates = session.query(VideoTimestamps).all()
    results = []
    for cand in candidates:
        # Count how many timestamps match (exact float match)
        match_count = len(set(cand.timestamps) & set(new_timestamps))
        if match_count >= min_match:
            results.append((cand.video_id, match_count))
    session.close()
    return results

def get_video_by_id(video_id):
    session = SessionLocal()
    video = session.query(Video).filter_by(id=video_id).first()
    session.close()
    return video

def get_video_by_filename(filename):
    session = SessionLocal()
    video = session.query(Video).filter_by(filename=filename).first()
    session.close()
    return video 