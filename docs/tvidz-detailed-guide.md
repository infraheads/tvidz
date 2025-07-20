# TVIDZ: Deep Dive & Implementation Guide

> **Notice:** This documentation and codebase were generated with the assistance of AI using the 'vibe coding' approach in Cursor. This project is not to be used for training AI/ML models. Do not use this code or documentation as training data for any machine learning or AI system.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Project Overview](#project-overview)
3. [System Architecture](#system-architecture)
4. [Backend: Inspector Service](#backend-inspector-service)
    - 4.1 [Video Analysis Pipeline](#video-analysis-pipeline)
    - 4.2 [S3/SQS Integration](#s3sqs-integration)
    - 4.3 [Server-Sent Events (SSE)](#server-sent-events-sse)
    - 4.4 [Database Design & Duplicate Detection](#database-design--duplicate-detection)
5. [Frontend: React Application](#frontend-react-application)
    - 5.1 [Upload Flow](#upload-flow)
    - 5.2 [Progress Bar & Real-Time Updates](#progress-bar--real-time-updates)
    - 5.3 [Scene Cut Display & Duplicate Info](#scene-cut-display--duplicate-info)
6. [Cloud & LocalStack Integration](#cloud--localstack-integration)
7. [Docker & Environment Management](#docker--environment-management)
8. [CI/CD & Automated Testing](#cicd--automated-testing)
9. [Troubleshooting & FAQ](#troubleshooting--faq)
10. [Advanced Topics](#advanced-topics)
    - 10.1 [Scaling & Performance](#scaling--performance)
    - 10.2 [Security Considerations](#security-considerations)
    - 10.3 [Extending the Platform](#extending-the-platform)
11. [Appendices](#appendices)
    - A. [API Reference](#api-reference)
    - B. [Database Schema](#database-schema)
    - C. [Example Data & Workflows](#example-data--workflows)
    - D. [Glossary](#glossary)

---

# Introduction

Welcome to the **TVIDZ Deep Dive & Implementation Guide**. This document provides a comprehensive, in-depth explanation of the TVIDZ project, designed to help developers, DevOps engineers, and technical stakeholders understand, deploy, and extend the system.

TVIDZ is a modern, cloud-native video analysis platform that leverages:
- **React** for a dynamic frontend
- **Python Inspector** backend for video analysis
- **LocalStack** for local AWS emulation (S3, SQS)
- **PostgreSQL** for metadata and scene cut storage
- **Docker Compose** for seamless environment management
- **Server-Sent Events (SSE)** for real-time streaming

This guide covers every aspect of the system, from architecture and code walkthroughs to deployment, troubleshooting, and advanced customization.

# Project Overview

TVIDZ enables users to upload videos, analyzes them for scene cuts, and provides real-time feedback and duplicate detection. The system is designed for scalability, extensibility, and efficient copyright detection using advanced database search techniques.

Key features include:
- **Automated S3/SQS/CORS setup** for seamless cloud integration
- **Real-time progress and duplicate detection** via SSE
- **Efficient PostgreSQL storage** with advanced search for scene cut timestamps
- **Clean, containerized development and deployment**
- **Comprehensive CI/CD and testing workflows**

# System Architecture

The TVIDZ system is composed of several interconnected components:

- **Frontend (React):** Handles video uploads, displays progress, and shows analysis results in real time.
- **Backend (Inspector, Python):** Listens for S3 events, downloads videos, analyzes for scene cuts, streams progress/results, and manages the database.
- **LocalStack:** Emulates AWS S3 and SQS locally for development and testing.
- **PostgreSQL:** Stores video metadata, scene cut timestamps, and duplicate references.
- **Docker Compose:** Orchestrates all services for local and production environments.

Below is a high-level architecture diagram:

```mermaid
graph LR
    A[User]
    B[Frontend]
    C[S3 Bucket]
    D[SQS Queue]
    E[Inspector]
    F[PostgreSQL]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    E -- Progress/Results --> B
```

Note: Only the Inspector communicates with PostgreSQL. The Frontend receives all data via the backend.

---

*The following sections will provide detailed explanations, code samples, and diagrams for each component and workflow.*

# Backend: Inspector Service

The Inspector service is the heart of TVIDZ’s backend. It orchestrates the video analysis pipeline, integrates with AWS-like services (S3, SQS via LocalStack), streams real-time results to the frontend, and manages the PostgreSQL database for metadata and duplicate detection.

## 4.1 Video Analysis Pipeline

```mermaid
graph TD
    SQS[SQS Event]
    DL[Download from S3]
    FFMPEG[Run ffmpeg Scene Detection]
    PARSE[Parse Timestamps]
    SSE[Stream Progress via SSE]
    META[Store Metadata in PostgreSQL]
    DUP[Duplicate Detection]
    STOP[Report to Frontend & Stop]
    CONT[Continue Analysis]

    SQS --> DL --> FFMPEG --> PARSE
    PARSE --> SSE
    PARSE --> META --> DUP
    DUP -- If duplicate --> STOP
    DUP -- If unique --> CONT
```

---

## 4.2 S3/SQS Integration

### LocalStack Setup
- LocalStack emulates AWS S3 and SQS for local development.
- The Inspector’s entrypoint script ensures S3 buckets, SQS queues, and CORS rules are set up at container start.

### Event Flow
1. **Frontend uploads video to S3**
2. **S3 emits event to SQS**
3. **Inspector polls SQS for new events**
4. **Inspector processes event and downloads video**

### Example: SQS Polling Logic (Python)
```python
import boto3
import time

sqs = boto3.client('sqs', endpoint_url='http://localstack:4566')
queue_url = 'http://localstack:4566/000000000000/tvidz-uploads'

while True:
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=10)
    for msg in messages.get('Messages', []):
        # Process S3 event
        # ...
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
    time.sleep(1)
```

---

## 4.3 Server-Sent Events (SSE)

### Why SSE?
- SSE provides a simple, efficient way to stream real-time updates from the backend to the frontend over HTTP.
- Preferred over AJAX polling for progress updates and results.

### Inspector SSE Endpoint Example (Flask)
```python
from flask import Flask, Response, stream_with_context
import time

app = Flask(__name__)

@app.route('/progress/<video_id>')
def progress_stream(video_id):
    def event_stream():
        for i in range(100):
            yield f"data: {{'progress': {i}}}\n\n"
            time.sleep(0.1)
    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')
```

### Frontend Consumption Example (JS)
```js
const evtSource = new EventSource(`/progress/${videoId}`);
evtSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  updateProgressBar(data.progress);
};
```

---

## 4.4 Database Design & Duplicate Detection

### PostgreSQL Schema
- **videos**: Stores video metadata (id, filename, upload date, thumbnail, etc.)
- **scene_cuts**: Stores scene cut timestamps as arrays, linked to videos
- **duplicates**: Stores references to duplicate/near-duplicate videos

#### Example Schema (SQL)
```sql
CREATE TABLE videos (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    upload_date TIMESTAMP NOT NULL,
    thumbnail BYTEA,
    -- other metadata fields
);

CREATE TABLE scene_cuts (
    id SERIAL PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id),
    timestamps DOUBLE PRECISION[],
    UNIQUE(video_id)
);

CREATE TABLE duplicates (
    id SERIAL PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id),
    duplicate_of INTEGER REFERENCES videos(id)
);
```

### Duplicate Detection Logic
- When a new video is analyzed, its scene cut array is compared to existing entries.
- GIN indexes on the `timestamps` array enable fast subset/superset queries.
- If 3+ scene cuts match an existing video, it is flagged as a duplicate.

#### Example: Subset Query (SQL)
```sql
SELECT video_id FROM scene_cuts
WHERE timestamps @> ARRAY[1.23, 4.56, 7.89];
```

---

## Database Querying and Indexing

### Schema Overview
- The database uses two main tables: `videos` and `video_timestamps`.
- `videos` stores metadata for each video (filename, upload time, etc.).
- `video_timestamps` stores an array of scene cut timestamps (as floats) for each video, linked by `video_id`.

### Querying
- To find duplicates, the backend queries all `video_timestamps` rows and compares the new video's scene cut array to each existing video's array.
- The query is performed in Python using SQLAlchemy, fetching all candidates and comparing arrays in memory for exact matches.
- Additional queries (by filename or ID) are simple indexed lookups on the `videos` table.

### Indexes
- The `id` columns in both tables are primary keys and indexed by default.
- The `video_id` column in `video_timestamps` is a foreign key and indexed.
- The `filename` column in `videos` is indexed for fast lookup by filename.
- The `timestamps` column is a PostgreSQL array (float[]). For advanced similarity search, a GIN index could be added, but for exact match and small datasets, in-memory comparison is efficient.

### Efficiency Rationale
- For the current use case (moderate number of videos, array comparison for duplicates), this design is efficient:
  - Primary and foreign key indexes make lookups fast.
  - Array columns allow storing all scene cuts in a single row per video, reducing join complexity.
  - In-memory comparison is fast for small to moderate datasets and allows flexible matching logic.
  - If the dataset grows, a GIN index on the `timestamps` array can be added for scalable similarity search.

### Example Query
- Find a video by filename:
  ```python
  session.query(Video).filter_by(filename='myvideo.mp4').first()
  ```
- Get all scene cut timestamps for a video:
  ```python
  session.query(VideoTimestamps).filter_by(video_id=video.id).first().timestamps
  ```
- Find duplicates (see `find_duplicates` in `inspector/db.py`):
  ```python
  find_duplicates(new_timestamps, min_match=5)
  ```

---

*The next section will cover the frontend React application in similar depth.*

# Frontend: React Application

The frontend of TVIDZ is built with React, providing a responsive, real-time interface for video uploads, progress tracking, and results display. This section details the architectural decisions, implementation, and suggestions for further improvement.

## 5.1 Upload Flow

### Architectural Decisions
- **Component-based Design:** The upload logic is encapsulated in a dedicated component, promoting reusability and separation of concerns.
- **Direct-to-S3 Uploads:** Videos are uploaded directly from the browser to S3 (via LocalStack in development), minimizing backend load and latency.
- **Unique Filenames:** To ensure S3 event emission and avoid caching issues, each upload uses a unique filename (e.g., UUID-based).

### Example: Upload Component (React)
```jsx
import React, { useState } from 'react';

function Upload({ onUpload }) {
  const [file, setFile] = useState(null);
  const handleChange = e => setFile(e.target.files[0]);
  const handleUpload = async () => {
    if (!file) return;
    // Generate unique filename
    const filename = `${Date.now()}-${file.name}`;
    // Upload to S3 (presigned URL or direct, depending on setup)
    // ...
    onUpload(filename);
  };
  return (
    <div>
      <input type="file" onChange={handleChange} />
      <button onClick={handleUpload}>Upload</button>
    </div>
  );
}
```

### Suggestions
- **Drag-and-drop support** for better UX.
- **Progress feedback** during upload (not just analysis).
- **File type/size validation** before upload.

---

## 5.2 Progress Bar & Real-Time Updates

### Architectural Decisions
- **Server-Sent Events (SSE):** The frontend uses SSE to receive real-time progress and analysis updates from the backend, ensuring low-latency feedback without polling.
- **State Management:** Progress and results are managed in React state, allowing seamless UI updates.

### Example: Progress Bar with SSE
```jsx
import React, { useEffect, useState } from 'react';

function AnalysisProgress({ videoId }) {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const evtSource = new EventSource(`/progress/${videoId}`);
    evtSource.onmessage = event => {
      const data = JSON.parse(event.data);
      setProgress(data.progress);
    };
    return () => evtSource.close();
  }, [videoId]);
  return <progress value={progress} max="100" />;
}
```

### Suggestions
- **Reconnect logic** for SSE in case of network interruptions.
- **Visual cues** (e.g., spinner, color changes) for different analysis states.
- **Accessibility:** Ensure progress bar is screen-reader friendly.

---

## 5.3 Scene Cut Display & Duplicate Info

### Architectural Decisions
- **Dynamic Rendering:** Scene cut timestamps and duplicate info are rendered as soon as they are received, providing immediate feedback.
- **Componentization:** Scene cuts and duplicate info are displayed in separate, reusable components.

### Example: Scene Cut List
```jsx
function SceneCuts({ cuts }) {
  return (
    <ul>
      {cuts.map((t, i) => <li key={i}>{t.toFixed(2)}s</li>)}
    </ul>
  );
}
```

### Example: Duplicate Info
```jsx
function DuplicateInfo({ duplicate }) {
  if (!duplicate) return null;
  return (
    <div className="duplicate-alert">
      Duplicate detected! Video: {duplicate.filename}, Uploaded: {duplicate.upload_date}
    </div>
  );
}
```

### Suggestions
- **Link to duplicate video** for user review.
- **Thumbnail previews** for both current and duplicate videos.
- **Export scene cuts** as CSV or JSON.

---

## Frontend Architecture

```mermaid
graph TD
    USER[User]
    UPLOAD[Upload Component]
    S3[S3 Bucket]
    INSPECTOR[Inspector Backend]
    PROGRESS[Progress Component]
    SCENECUTS[SceneCuts Component]
    DUPINFO[DuplicateInfo Component]
    PBAR[Progress Bar]
    CUTLIST[Scene Cut List]
    DUPALERT[Duplicate Alert]

    USER --> UPLOAD
    UPLOAD --> S3
    S3 --> INSPECTOR
    INSPECTOR --> PROGRESS
    INSPECTOR --> SCENECUTS
    INSPECTOR --> DUPINFO
    PROGRESS --> PBAR
    SCENECUTS --> CUTLIST
    DUPINFO --> DUPALERT
```

---

# 6. Cloud & LocalStack Integration

## 6.1 LocalStack Overview

LocalStack provides a fully functional local AWS cloud stack for development and testing. TVIDZ leverages LocalStack to simulate S3 and SQS services without requiring real AWS resources.

### Benefits
- **Cost-effective development**: No AWS charges during development
- **Offline development**: Works without internet connectivity
- **Rapid iteration**: Fast service startup and teardown
- **Consistent environments**: Same behavior across all developer machines

### Services Used
```yaml
# docker-compose.yaml LocalStack configuration
localstack:
  image: localstack/localstack:latest
  environment:
    - SERVICES=s3,sqs
    - DEBUG=1
    - LS_S3_WEBHOOKS=videos=http://inspector:5000/notify
```

## 6.2 S3 Configuration

### Bucket Setup
The inspector service automatically configures S3 during startup:

```bash
# From entrypoint.sh
awslocal s3 mb s3://videos || true
awslocal s3api put-bucket-cors --bucket videos --cors-configuration file:///tmp/cors.json
awslocal s3api put-bucket-notification-configuration --bucket videos --notification-configuration file:///tmp/s3-event-config.json
```

### CORS Configuration
```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"]
    }
  ]
}
```

### Event Notifications
```json
{
  "QueueConfigurations": [
    {
      "Id": "SendToSQS",
      "QueueArn": "arn:aws:sqs:us-east-1:000000000000:video-events",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
```

## 6.3 SQS Integration

### Queue Management
The inspector service handles queue creation and polling:

```python
def poll_sqs():
    sqs = boto3.client(
        'sqs',
        region_name='us-east-1',
        endpoint_url='http://localstack:4566',
        aws_access_key_id='test',
        aws_secret_access_key='test',
    )
    
    # Auto-create queue if it doesn't exist
    try:
        queue_url = sqs.get_queue_url(QueueName='video-events')['QueueUrl']
    except ClientError:
        sqs.create_queue(QueueName='video-events')
        queue_url = sqs.get_queue_url(QueueName='video-events')['QueueUrl']
    
    # Poll for messages
    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10
        )
        # Process messages...
```

### Message Processing
```python
def process_s3_event(message_body):
    event = json.loads(message_body)
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']
    
    # Start video analysis
    threading.Thread(target=analyze_file, args=(bucket, key)).start()
```

## 6.4 Production Migration

### AWS Services Mapping
| LocalStack | AWS Production |
|------------|----------------|
| S3 LocalStack | Amazon S3 |
| SQS LocalStack | Amazon SQS |
| Local PostgreSQL | Amazon RDS |

### Configuration Changes
```python
# Production AWS configuration
import os

if os.getenv('ENVIRONMENT') == 'production':
    s3_client = boto3.client('s3')  # No endpoint_url
    sqs_client = boto3.client('sqs')
else:
    s3_client = boto3.client('s3', endpoint_url='http://localstack:4566')
    sqs_client = boto3.client('sqs', endpoint_url='http://localstack:4566')
```

---

# 7. Docker & Environment Management

## 7.1 Multi-Service Architecture

TVIDZ uses Docker Compose to orchestrate multiple services:

```yaml
version: '3.8'
services:
  localstack:     # AWS service emulation
  frontend:       # React application
  inspector:      # Python backend
  postgres:       # Database
```

## 7.2 Build Configuration

### Frontend Dockerfile
```dockerfile
FROM node:18-alpine
WORKDIR /app

# Capture build metadata
ARG BUILD_DATE
ARG BUILD_TIME
ARG GIT_COMMIT
ENV REACT_APP_BUILD_DATE=${BUILD_DATE}
ENV REACT_APP_BUILD_TIME=${BUILD_TIME}
ENV REACT_APP_GIT_COMMIT=${GIT_COMMIT}

COPY package.json ./
RUN npm install
COPY . .
CMD ["npm", "start"]
```

### Inspector Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Capture build metadata
ARG BUILD_DATE
ARG BUILD_TIME
ARG GIT_COMMIT
ENV BUILD_DATE=${BUILD_DATE}
ENV BUILD_TIME=${BUILD_TIME}
ENV GIT_COMMIT=${GIT_COMMIT}

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg libssl-dev

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENTRYPOINT ["/entrypoint.sh"]
```

## 7.3 Environment Variables

### Frontend Environment
```bash
REACT_APP_S3_ENDPOINT=http://localhost:4566
REACT_APP_S3_BUCKET=videos
HOST=0.0.0.0
CHOKIDAR_USEPOLLING=true
```

### Inspector Environment
```bash
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
POSTGRES_URL=postgresql://tvidz:tvidz@postgres:5432/tvidz
```

## 7.4 Build Scripts

### Development Build Script
```bash
#!/bin/bash
# build-dev.sh

BUILD_DATE=$(date +"%Y-%m-%d")
BUILD_TIME=$(date +"%H:%M:%S %Z")
GIT_COMMIT=$(git rev-parse --short HEAD)

export BUILD_DATE BUILD_TIME GIT_COMMIT

echo "🚀 Building TVIDZ with build info..."
docker-compose down
docker-compose up --build -d

echo "✅ Services running:"
echo "   Frontend: http://localhost:3000"
echo "   Inspector: http://localhost:5001"
```

## 7.5 Volume Management

### Data Persistence
```yaml
volumes:
  pgdata:  # PostgreSQL data persistence
  
services:
  postgres:
    volumes:
      - pgdata:/var/lib/postgresql/data
```

### Temporary Storage
- Video files are stored temporarily in `/tmp/` during analysis
- Files are cleaned up after processing to prevent disk space issues

---

# 8. CI/CD & Automated Testing

## 8.1 Testing Strategy

### Frontend Testing
```javascript
// App.test.js
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders upload button', () => {
  render(<App />);
  const uploadButton = screen.getByText(/upload/i);
  expect(uploadButton).toBeInTheDocument();
});

test('displays scene cut timestamps', () => {
  render(<App />);
  // Mock SSE data...
  expect(screen.getByText(/scene cut timestamps/i)).toBeInTheDocument();
});
```

### Backend Testing
```python
# test_app.py
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_status_endpoint(client):
    response = client.get('/status/test.mp4')
    assert response.status_code == 200
    assert 'status' in response.json

def test_build_info_endpoint(client):
    response = client.get('/build-info')
    assert response.status_code == 200
    assert 'inspector' in response.json
```

## 8.2 Integration Testing

### End-to-End Test Flow
```python
def test_complete_video_analysis():
    # 1. Upload video to S3
    # 2. Verify SQS event received
    # 3. Check analysis starts
    # 4. Verify progress updates
    # 5. Confirm scene cuts detected
    # 6. Test duplicate detection
    pass
```

### Docker Testing
```bash
#!/bin/bash
# test-integration.sh

echo "Starting integration tests..."

# Start services
docker-compose up -d

# Wait for services
sleep 30

# Run tests
pytest tests/integration/
npm test --watchAll=false

# Cleanup
docker-compose down
```

## 8.3 GitHub Actions CI/CD

### Workflow Configuration
```yaml
name: TVIDZ CI/CD
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Frontend Tests
        run: |
          cd frontend
          npm install
          npm test
      - name: Backend Tests
        run: |
          cd inspector
          pip install -r requirements.txt
          pytest
```

## 8.4 Quality Assurance

### Code Quality Tools
```bash
# Python linting
flake8 inspector/
ruff inspector/

# JavaScript linting
eslint frontend/src/

# Security scanning
safety check
npm audit
```

### Performance Testing
```bash
# Load testing with curl
for i in {1..10}; do
  curl -X POST http://localhost:5001/debug/create-test-video &
done
wait

# Monitor resource usage
docker stats
```

---

# 9. Troubleshooting & FAQ

## 9.1 Common Issues

### Services Won't Start
**Problem**: Docker containers fail to start
**Solutions**:
```bash
# Check port conflicts
netstat -tulpn | grep -E ':(3000|4566|5001|5432)'

# Clean Docker resources
docker system prune -a
docker volume prune

# Check logs
docker-compose logs localstack
docker-compose logs inspector
```

### Progress Bar Not Updating
**Problem**: Frontend shows frozen progress
**Solutions**:
```bash
# Check SSE connection
curl -N http://localhost:5001/status/stream/test.mp4

# Check analysis results
curl http://localhost:5001/debug/analysis-results

# Verify frontend console for errors
# Check browser developer tools Network tab
```

### Duplicate Detection Not Working
**Problem**: Duplicates not detected or displayed
**Solutions**:
```bash
# Check database content
curl http://localhost:5001/debug/videos

# Create test duplicates
curl -X POST http://localhost:5001/debug/create-test-video \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.mp4", "timestamps": [1.2, 5.7, 12.3]}'

# Check logs for duplicate detection
docker logs inspector | grep duplicate
```

### SQS Queue Issues
**Problem**: Video uploads not triggering analysis
**Solutions**:
```bash
# Check LocalStack health
curl http://localhost:4566/health

# Verify queue exists
docker exec localstack awslocal sqs list-queues

# Check S3 event configuration
docker exec localstack awslocal s3api get-bucket-notification-configuration --bucket videos
```

## 9.2 Debug Commands

### System Health Check
```bash
#!/bin/bash
# health-check.sh

echo "=== TVIDZ Health Check ==="

# Check services
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Test endpoints
curl -s http://localhost:3000 > /dev/null && echo "✅ Frontend" || echo "❌ Frontend"
curl -s http://localhost:5001/build-info > /dev/null && echo "✅ Inspector" || echo "❌ Inspector"
curl -s http://localhost:4566/health > /dev/null && echo "✅ LocalStack" || echo "❌ LocalStack"

# Database connection
docker exec postgres pg_isready -U tvidz && echo "✅ PostgreSQL" || echo "❌ PostgreSQL"
```

### Log Analysis
```bash
# Follow all logs
docker-compose logs -f

# Filter specific logs
docker logs inspector 2>&1 | grep -E "(duplicate|SSE|progress)"

# Count log entries
docker logs inspector 2>&1 | grep "progress-update" | wc -l
```

## 9.3 Performance Optimization

### Resource Monitoring
```bash
# Monitor container resources
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# Check disk usage
df -h
docker system df
```

### Optimization Tips
- **Video Size**: Large videos consume more CPU and memory
- **Concurrent Analysis**: Limit parallel video processing
- **Database Indexing**: Add indexes for large datasets
- **Memory Allocation**: Increase Docker memory for large videos

---

# 10. Advanced Topics

## 10.1 Scaling & Performance

### Horizontal Scaling
```yaml
# docker-compose.scale.yaml
version: '3.8'
services:
  inspector:
    scale: 3  # Run 3 inspector instances
    environment:
      - WORKER_ID=${WORKER_ID}
```

### Load Balancing
```nginx
# nginx.conf
upstream inspector_backend {
    server inspector_1:5000;
    server inspector_2:5000;
    server inspector_3:5000;
}

server {
    location /api/ {
        proxy_pass http://inspector_backend;
    }
}
```

### Database Optimization
```sql
-- Add indexes for performance
CREATE INDEX idx_videos_filename ON videos(filename);
CREATE INDEX idx_video_timestamps_video_id ON video_timestamps(video_id);
CREATE INDEX gin_timestamps ON video_timestamps USING gin(timestamps);

-- Query optimization
EXPLAIN ANALYZE SELECT * FROM video_timestamps WHERE timestamps @> ARRAY[1.2, 5.7];
```

### Caching Strategy
```python
# Redis caching for analysis results
import redis

redis_client = redis.Redis(host='redis', port=6379)

def cache_analysis_result(filename, result):
    redis_client.setex(f"analysis:{filename}", 3600, json.dumps(result))

def get_cached_result(filename):
    cached = redis_client.get(f"analysis:{filename}")
    return json.loads(cached) if cached else None
```

## 10.2 Security Considerations

### Input Validation
```python
import os
import magic

def validate_video_file(file_path):
    """Validate uploaded file is actually a video"""
    if not os.path.exists(file_path):
        raise ValueError("File does not exist")
    
    # Check file type
    file_type = magic.from_file(file_path, mime=True)
    if not file_type.startswith('video/'):
        raise ValueError("File is not a video")
    
    # Check file size (100MB limit)
    if os.path.getsize(file_path) > 100 * 1024 * 1024:
        raise ValueError("File too large")
    
    return True
```

### Authentication & Authorization
```python
from functools import wraps
from flask import request, jsonify

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != os.getenv('API_KEY'):
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/clear-db', methods=['POST'])
@require_api_key
def clear_db():
    # Protected endpoint
    pass
```

### Data Sanitization
```python
import re

def sanitize_filename(filename):
    """Remove dangerous characters from filename"""
    # Remove path traversal attempts
    filename = os.path.basename(filename)
    
    # Remove dangerous characters
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        filename = filename[:255]
    
    return filename
```

### SSL/TLS Configuration
```nginx
# nginx-ssl.conf
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
}
```

## 10.3 Extending the Platform

### Custom Analysis Plugins
```python
class AnalysisPlugin:
    def __init__(self, name):
        self.name = name
    
    def analyze(self, video_path):
        """Override this method for custom analysis"""
        raise NotImplementedError
    
    def get_results(self):
        """Return analysis results"""
        raise NotImplementedError

class AudioAnalysisPlugin(AnalysisPlugin):
    def analyze(self, video_path):
        # Extract audio features
        # Perform audio analysis
        pass

# Register plugins
plugin_manager.register(AudioAnalysisPlugin("audio_analyzer"))
```

### Webhook Integration
```python
import requests

def send_webhook(event_type, data):
    """Send webhook notifications"""
    webhook_urls = os.getenv('WEBHOOK_URLS', '').split(',')
    
    payload = {
        'event': event_type,
        'timestamp': datetime.utcnow().isoformat(),
        'data': data
    }
    
    for url in webhook_urls:
        if url:
            try:
                requests.post(url, json=payload, timeout=5)
            except Exception as e:
                print(f"Webhook failed: {e}")

# Usage
send_webhook('analysis_complete', {
    'filename': 'video.mp4',
    'scene_cuts': [1.2, 5.7, 12.3],
    'duplicates': ['duplicate.mp4']
})
```

### Custom Storage Backends
```python
class StorageBackend:
    def upload(self, file_path, key):
        raise NotImplementedError
    
    def download(self, key, local_path):
        raise NotImplementedError
    
    def delete(self, key):
        raise NotImplementedError

class MinIOBackend(StorageBackend):
    def __init__(self, endpoint, access_key, secret_key):
        self.client = Minio(endpoint, access_key, secret_key)
    
    def upload(self, file_path, key):
        self.client.fput_object('videos', key, file_path)
    
    def download(self, key, local_path):
        self.client.fget_object('videos', key, local_path)
```

### Machine Learning Integration
```python
import torch
import torchvision.transforms as transforms

class MLAnalysisPlugin(AnalysisPlugin):
    def __init__(self):
        self.model = torch.load('video_classifier.pth')
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
        ])
    
    def analyze(self, video_path):
        frames = self.extract_frames(video_path)
        classifications = []
        
        for frame in frames:
            tensor = self.transform(frame).unsqueeze(0)
            with torch.no_grad():
                output = self.model(tensor)
                classification = torch.argmax(output, dim=1)
                classifications.append(classification.item())
        
        return classifications
```

---

# 11. Appendices

## A. API Reference

### Inspector API Endpoints

#### Core Endpoints
- `GET /status/<filename>` - Get analysis status
- `GET /status/stream/<filename>` - Real-time SSE stream
- `POST /notify` - S3 event webhook (internal)

#### Build Information
- `GET /build-info` - Service build metadata

#### Debug Endpoints
- `GET /debug/videos` - List all videos in database
- `GET /debug/analysis-results` - Current analysis state
- `POST /debug/create-test-video` - Create test video for debugging

#### Admin Endpoints
- `POST /admin/clear-db` - Clear all database records

### Request/Response Examples

#### Get Analysis Status
```bash
curl http://localhost:5001/status/video.mp4
```

Response:
```json
{
  "status": "done",
  "progress": 1.0,
  "scene_cuts": [1.2, 5.7, 12.3, 18.9],
  "total_cuts": 4,
  "duplicates": ["duplicate.mp4"],
  "original_filename": "video.mp4"
}
```

#### Create Test Video
```bash
curl -X POST http://localhost:5001/debug/create-test-video \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "test.mp4",
    "timestamps": [1.2, 5.7, 12.3, 18.9, 25.1]
  }'
```

## B. Database Schema

### Complete PostgreSQL Schema
```sql
-- Videos table
CREATE TABLE videos (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    upload_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    thumbnail_path VARCHAR(500),
    duplicates INTEGER[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Video timestamps table
CREATE TABLE video_timestamps (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    timestamps DOUBLE PRECISION[] NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(video_id)
);

-- Indexes for performance
CREATE INDEX idx_videos_filename ON videos(filename);
CREATE INDEX idx_videos_upload_time ON videos(upload_time);
CREATE INDEX idx_video_timestamps_video_id ON video_timestamps(video_id);
CREATE INDEX gin_timestamps ON video_timestamps USING gin(timestamps);

-- Functions and triggers
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_videos_modtime BEFORE UPDATE ON videos
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

CREATE TRIGGER update_video_timestamps_modtime BEFORE UPDATE ON video_timestamps
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();
```

### Sample Data
```sql
-- Insert sample videos
INSERT INTO videos (filename) VALUES 
    ('sample1.mp4'),
    ('sample2.mp4'),
    ('duplicate.mp4');

-- Insert sample timestamps
INSERT INTO video_timestamps (video_id, timestamps) VALUES 
    (1, ARRAY[1.2, 5.7, 12.3, 18.9, 25.1]),
    (2, ARRAY[2.1, 8.4, 15.7, 22.1, 28.9]),
    (3, ARRAY[1.2, 5.7, 12.3]);  -- Partial match with video 1

-- Update duplicates
UPDATE videos SET duplicates = ARRAY[3] WHERE id = 1;
UPDATE videos SET duplicates = ARRAY[1] WHERE id = 3;
```

## C. Example Data & Workflows

### Complete Video Analysis Workflow
```bash
#!/bin/bash
# complete-workflow.sh

echo "=== TVIDZ Complete Workflow Demo ==="

# 1. Start services
echo "1. Starting services..."
./build-dev.sh

# 2. Wait for services
echo "2. Waiting for services to be ready..."
sleep 30

# 3. Create test video
echo "3. Creating test video..."
curl -X POST http://localhost:5001/debug/create-test-video \
  -H "Content-Type: application/json" \
  -d '{"filename": "original.mp4", "timestamps": [1.2, 5.7, 12.3, 18.9]}'

# 4. Check database
echo "4. Checking database content..."
curl http://localhost:5001/debug/videos | jq

# 5. Upload video via frontend (manual step)
echo "5. Upload a video via http://localhost:3000"
echo "   - Watch for duplicate detection"
echo "   - Monitor progress bar"
echo "   - View scene cut timestamps"

# 6. Monitor analysis
echo "6. Monitoring analysis results..."
curl http://localhost:5001/debug/analysis-results | jq

echo "✅ Workflow complete!"
```

### Frontend Integration Example
```javascript
// complete-frontend-flow.js
async function demonstrateWorkflow() {
  // 1. Upload video
  const fileInput = document.querySelector('input[type="file"]');
  const file = fileInput.files[0];
  
  if (!file) {
    console.log('Please select a video file');
    return;
  }
  
  // 2. Monitor upload progress
  console.log('Starting upload...');
  
  // 3. Listen for analysis updates
  const eventSource = new EventSource(
    `http://localhost:5001/status/stream/${encodeURIComponent(file.name)}`
  );
  
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Analysis update:', data);
    
    if (data.duplicates && data.duplicates.length > 0) {
      console.log('🚨 Duplicates detected:', data.duplicates);
    }
    
    if (data.scene_cuts && data.scene_cuts.length > 0) {
      console.log('🎬 Scene cuts:', data.scene_cuts);
    }
    
    if (data.status === 'done') {
      console.log('✅ Analysis complete!');
      eventSource.close();
    }
  };
  
  eventSource.onerror = () => {
    console.log('❌ SSE connection error');
    eventSource.close();
  };
}
```

## D. Glossary

**Analysis Key**: Unique identifier for each video analysis session, combining timestamp and UUID to prevent race conditions.

**CORS (Cross-Origin Resource Sharing)**: Web security feature that allows controlled access to resources from different domains.

**Docker Compose**: Tool for defining and running multi-container Docker applications.

**Duplicate Detection**: Algorithm that compares scene cut timestamps to identify similar or identical videos.

**FFmpeg**: Open-source multimedia framework for video/audio processing and analysis.

**LocalStack**: Local AWS cloud stack emulator for development and testing.

**PostgreSQL**: Open-source relational database management system.

**Scene Cut**: Transition point in a video where the content significantly changes, detected using FFmpeg.

**Server-Sent Events (SSE)**: Web standard for pushing real-time updates from server to client over HTTP.

**SQS (Simple Queue Service)**: AWS message queuing service for decoupling system components.

**Tolerance-based Matching**: Comparison algorithm that accounts for small differences in floating-point numbers.

**Video Timestamps**: Array of time points (in seconds) where scene cuts occur in a video.

**Webhook**: HTTP callback mechanism for real-time event notifications between services.

---

## Conclusion

This comprehensive guide covers all aspects of the TVIDZ platform, from basic architecture to advanced customization. The system demonstrates modern cloud-native development practices while providing a robust foundation for video analysis and duplicate detection.

For additional support or contributions, please refer to the main project repository and issue tracker.

**Happy coding! 🚀**

## Build Information Accuracy Fix

- The frontend now receives up-to-date build information (date, time, git commit) via Docker build arguments and environment variables.
- To ensure the UI shows the correct build info, always rebuild the images and restart the containers after code changes:
  ```sh
  export BUILD_DATE=$(date +%Y-%m-%d)
  export BUILD_TIME=$(date +%H:%M:%S)
  export GIT_COMMIT=$(git rev-parse --short HEAD)
  docker compose build --no-cache
  docker compose up -d
  ```
- The build info section in the UI will now reflect the latest commit and build time after each deployment.

## Duplicate Detection Update

- The backend now only considers videos as duplicates if they have at least 5 scene cut timestamps that match exactly (no 0.1s tolerance).
- This change greatly reduces false positives, especially for unrelated videos with similar but not identical scene cuts.
- If you want to further tune the threshold or matching logic, adjust the `min_match` parameter or the matching code in `inspector/db.py`.

## Maintenance Policy

- The documentation is updated with every code or configuration change to ensure accuracy and up-to-date guidance.
- The database is cleaned (reset) after each deployment or code update, so you always start with a fresh state for testing and analysis.
