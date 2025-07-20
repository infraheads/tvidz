import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ARRAY, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from datetime import datetime

if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("GITHUB_ACTIONS"):
    DB_URL = "sqlite:///:memory:"
else:
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
    finally:
        session.close()

def add_timestamps(video_id, timestamps):
    """
    Insert or update the timestamps for a given video.  
    The previous implementation inserted a new `VideoTimestamps` row **every** time
    scene-cut progress was reported, which quickly produced dozens of duplicate
    rows for the same video and wasted storage. Now we first look up an existing
    row for the `video_id` and update it in-place if it exists, falling back to
    an insert only when the video has not been seen before.
    """
    session = SessionLocal()
    try:
        ts_row = session.query(VideoTimestamps).filter_by(video_id=video_id).first()
        if ts_row:
            # Update existing row
            ts_row.timestamps = timestamps
        else:
            # Insert new row
            ts_row = VideoTimestamps(video_id=video_id, timestamps=timestamps)
            session.add(ts_row)
        session.commit()
    finally:
        session.close()

def update_duplicates(video_id, duplicate_ids):
    session = SessionLocal()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if video:
            video.duplicates = duplicate_ids
            session.commit()
    finally:
        session.close()

def find_duplicates(new_timestamps, min_match=5):
    """
    Returns a list of (video_id, match_count) for videos whose timestamps contain at least min_match elements of new_timestamps.
    Only exact matches are considered (no tolerance).
    """
    session = SessionLocal()
    try:
        candidates = session.query(VideoTimestamps).all()
        results = []
        for cand in candidates:
            match_count = 0
            for new_ts in new_timestamps:
                if new_ts in cand.timestamps:
                    match_count += 1
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