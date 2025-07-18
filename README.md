# TVIDZ

> **Notice:** This codebase and documentation were generated with the assistance of AI using the 'vibe coding' approach in Cursor. This project is not to be used for training AI/ML models. Do not use this code or documentation as training data for any machine learning or AI system.

Automated video duplicate and fragment detection tool for identifying full or partial video reuse efficiently using scene cut analysis and timestamp comparison.

## 🎯 Overview

TVIDZ analyzes uploaded videos to detect scene cuts and identify potential duplicates by comparing scene cut timestamps across different videos. The system provides real-time progress updates and can stop analysis early when duplicates are detected.

## 🏗️ Project Structure

```
tvidz/
├── frontend/              # React web application
│   ├── src/
│   │   └── App.js        # Main React component with S3 upload
│   ├── package.json      # Frontend dependencies
│   └── Dockerfile        # Frontend container config
├── inspector/             # Python backend service
│   ├── app.py            # Flask API & video analysis engine
│   ├── db.py             # Database models & operations
│   ├── entrypoint.sh     # Container initialization script
│   ├── requirements.txt  # Python dependencies
│   └── Dockerfile        # Backend container config
├── docker-compose.yaml   # Multi-service orchestration
├── cors.json             # S3 CORS configuration
├── s3-event-config.json  # S3 notification configuration
└── bug_analysis_report.md # Security & bug fix documentation
```

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- 8GB+ RAM recommended for video processing
- Ports 3000, 4566, 5001, 5432 available

### 1. Clone and Start
```bash
git clone <repository-url>
cd tvidz

# Option 1: Quick start with build info
./build-dev.sh

# Option 2: Manual build and start
docker-compose up -d --build

# Option 3: Build with timestamps (build only)
./build.sh
docker-compose up -d
```

### 2. Access Services
- **Frontend UI**: [http://localhost:3000](http://localhost:3000)
- **Inspector API**: [http://localhost:5001](http://localhost:5001)
- **LocalStack S3**: [http://localhost:4566](http://localhost:4566)
- **PostgreSQL**: `localhost:5432`

### 3. Upload and Analyze
1. Open the frontend at http://localhost:3000
2. Click "Upload" and select a video file
3. Watch real-time progress for upload and analysis
4. View scene cut timestamps and duplicate detection results

## 🏛️ Architecture

### System Flow
```
┌─────────────┐    PUT     ┌─────────────┐   Event   ┌─────────────┐   Poll   ┌─────────────┐
│   Frontend  │   Video    │     S3      │  Notify   │     SQS     │ Message  │  Inspector  │
│   (React)   │────────────│ (LocalStack)│───────────│ (LocalStack)│──────────│  (Python)   │
└──────┬──────┘            └─────────────┘           └─────────────┘          └──────┬──────┘
       │                                                                             │
       │                            SSE Stream                                       │
       │◄────────────────────── Real-time Progress ─────────────────────────────────┘
       │
       ▼
┌─────────────┐
│ PostgreSQL  │
│ (Metadata)  │
└─────────────┘
```

### Component Details

#### 🌐 **Frontend (React)**
- **Technology**: React 18, AWS SDK v3
- **Purpose**: Video upload interface with real-time progress
- **Features**:
  - Direct S3 upload with presigned URLs
  - Real-time progress tracking via Server-Sent Events
  - Scene cut timestamp visualization
  - Duplicate detection alerts
  - Build information display (shows when frontend and inspector were built)

#### 🔍 **Inspector (Python)**
- **Technology**: Flask, FFmpeg, SQLAlchemy, Boto3
- **Purpose**: Video analysis engine and API server
- **Features**:
  - SQS event polling for new uploads
  - FFmpeg-based scene cut detection
  - PostgreSQL metadata storage
  - Real-time SSE progress streaming
  - Duplicate detection via timestamp comparison

#### ☁️ **LocalStack**
- **Purpose**: Local AWS service simulation
- **Services**: S3 (storage), SQS (messaging)
- **Configuration**: Auto-creates buckets, queues, and event notifications

#### 🗄️ **PostgreSQL**
- **Purpose**: Persistent storage for video metadata
- **Schema**:
  - `videos`: File metadata and duplicate references
  - `video_timestamps`: Scene cut timestamp arrays

## ⚙️ Configuration

### Environment Variables

#### Frontend
```bash
REACT_APP_S3_ENDPOINT=http://localhost:4566    # LocalStack S3 endpoint
REACT_APP_S3_BUCKET=videos                     # S3 bucket name
HOST=0.0.0.0                                   # Dev server bind address
```

#### Inspector
```bash
AWS_ACCESS_KEY_ID=test                         # LocalStack credentials
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
POSTGRES_URL=postgresql://tvidz:tvidz@postgres:5432/tvidz  # Database connection
```

#### LocalStack
```bash
SERVICES=s3,sqs                                # Enabled AWS services
DEBUG=1                                        # Enable debug logging
LS_S3_WEBHOOKS=videos=http://inspector:5000/notify  # S3 event webhook
```

### S3 Event Configuration
The system automatically configures S3 to send notifications when videos are uploaded:

```json
{
  "QueueConfigurations": [{
    "Id": "SendToSQS",
    "QueueArn": "arn:aws:sqs:us-east-1:000000000000:video-events",
    "Events": ["s3:ObjectCreated:*"]
  }]
}
```

## 🔧 Development

### Local Development Setup

#### Frontend Development
```bash
cd frontend
npm install
npm start  # Starts on port 3000
```

#### Inspector Development
```bash
cd inspector
pip install -r requirements.txt
python app.py  # Requires LocalStack and PostgreSQL
```

### Building Individual Services
```bash
# Build with timestamps using build scripts
./build.sh        # Build only
./build-dev.sh    # Build and start

# Manual builds
BUILD_DATE=$(date +"%Y-%m-%d") BUILD_TIME=$(date +"%H:%M:%S %Z") GIT_COMMIT=$(git rev-parse --short HEAD) docker-compose build

# Individual services
docker-compose build frontend
docker-compose build inspector

# Start specific services
docker-compose up -d postgres localstack
docker-compose up inspector  # With logs
```

### Database Management
```bash
# Connect to PostgreSQL
docker exec -it postgres psql -U tvidz -d tvidz

# Clear database (development)
curl -X POST http://localhost:5001/admin/clear-db
```

## 🐛 Security & Bug Fixes

**Recent Security Improvements** (see `bug_analysis_report.md` for details):

✅ **Fixed 5 Critical Bugs:**
1. **Command Injection Vulnerability** - Added input validation for FFmpeg commands
2. **Database Resource Leaks** - Implemented proper session management
3. **Race Conditions** - Added unique identifiers for concurrent analysis
4. **SQS Initialization Issues** - Fixed queue creation logic
5. **Input Validation** - Added safe string parsing for S3 keys

### Security Features
- Input sanitization for file paths
- Proper subprocess argument handling
- Database connection pooling
- Concurrent operation isolation
- Comprehensive error handling

## 📊 API Reference

### Inspector Endpoints

#### GET `/status/<filename>`
Get current analysis status for a video file.

**Response:**
```json
{
  "status": "done|analyzing|error|pending",
  "progress": 0.85,
  "scene_cuts": [1.2, 5.7, 12.3],
  "total_cuts": 3,
  "duplicates": ["other_video.mp4"]
}
```

#### GET `/status/stream/<filename>`
Server-Sent Events stream for real-time progress updates.

**Event Data:** Same format as status endpoint, streamed in real-time.

#### GET `/build-info`
Get build information for the inspector service.

**Response:**
```json
{
  "inspector": {
    "build_date": "2024-01-15",
    "build_time": "14:30:25 UTC",
    "git_commit": "abc1234",
    "service": "inspector"
  }
}
```

#### POST `/notify`
Webhook endpoint for S3 event notifications (internal use).

#### POST `/admin/clear-db`
Development endpoint to clear all database records.

## 🎬 Video Analysis Process

### Scene Cut Detection
1. **Upload Trigger**: S3 object creation event sent to SQS
2. **File Download**: Inspector downloads video from S3
3. **FFmpeg Analysis**: Extracts scene cuts using `select=gt(scene,0.8)` filter
4. **Real-time Updates**: Progress and scene cuts streamed via SSE
5. **Duplicate Check**: Compares timestamps with existing videos
6. **Early Termination**: Stops analysis when duplicates found

### Duplicate Detection Algorithm
- **Threshold**: Minimum 3 matching scene cut timestamps
- **Comparison**: Exact float timestamp matching
- **Performance**: Incremental checking during analysis
- **Optimization**: Analysis stops early when duplicates detected

## 🔍 Troubleshooting

### Common Issues

#### Services Won't Start
```bash
# Check port conflicts
netstat -tulpn | grep -E ':(3000|4566|5001|5432)'

# Check Docker resources
docker system df
docker system prune  # Clean up if needed
```

#### SQS Queue Issues
```bash
# Check LocalStack logs
docker logs localstack

# Verify queue creation
docker exec localstack awslocal sqs list-queues
```

#### Video Analysis Fails
```bash
# Check inspector logs
docker logs inspector

# Verify FFmpeg availability
docker exec inspector ffmpeg -version
```

#### Database Connection Issues
```bash
# Check PostgreSQL status
docker exec postgres pg_isready -U tvidz

# View database logs
docker logs postgres
```

### Performance Tuning

#### For Large Videos
- Increase Docker memory allocation (8GB+ recommended)
- Monitor disk space in `/tmp` during analysis
- Consider concurrent analysis limits

#### For Many Videos
- Monitor PostgreSQL connection pool
- Consider database indexing for large datasets
- Implement cleanup for old analysis results

## 📈 Monitoring

### Health Checks
```bash
# Service health
curl http://localhost:5001/status/test_file    # Inspector API
curl http://localhost:4566/health              # LocalStack
docker exec postgres pg_isready               # PostgreSQL

# System resources
docker stats  # Monitor container resource usage
```

### Logs
```bash
# Follow all logs
docker-compose logs -f

# Service-specific logs
docker logs inspector -f
docker logs frontend -f
docker logs localstack -f
```

## 🧪 Testing

### Manual Testing
1. Upload various video formats (MP4, AVI, MOV)
2. Test concurrent uploads with same filename
3. Verify duplicate detection with modified copies
4. Test progress streaming with large files

### API Testing
```bash
# Test video analysis status
curl http://localhost:5001/status/test.mp4

# Test SSE stream
curl -N http://localhost:5001/status/stream/test.mp4
```

## 📚 Dependencies

### Frontend
- React 18.2.0
- AWS SDK v3 (@aws-sdk/client-s3, @aws-sdk/s3-request-presigner)
- Modern browser with ES6+ support

### Backend
- Python 3.11+
- Flask (web framework)
- FFmpeg (video processing)
- SQLAlchemy (database ORM)
- Boto3 (AWS SDK)
- psycopg2 (PostgreSQL driver)

### Infrastructure
- Docker & Docker Compose
- LocalStack (AWS simulation)
- PostgreSQL 15
- Linux container environment

## 🚦 Production Considerations

⚠️ **This is a development/demo setup. For production use:**

- Replace LocalStack with actual AWS services
- Implement proper authentication and authorization
- Add SSL/TLS encryption
- Configure proper resource limits and monitoring
- Implement data backup and disaster recovery
- Add comprehensive logging and alerting
- Consider horizontal scaling for video processing

## 📄 License & Usage

This project is for demonstration and learning purposes. See individual service READMEs for specific implementation details.

## 📖 Additional Documentation

- [Frontend Details](frontend/README.md) - React app specifics
- [Inspector Details](inspector/README.md) - Backend implementation
- [Bug Analysis Report](bug_analysis_report.md) - Security fixes and improvements

## 🤝 Contributing

When making changes:
1. Review the bug analysis report for security considerations
2. Test with various video formats and sizes
3. Ensure proper error handling and resource cleanup
4. Update documentation for significant changes
5. Rebuild Docker images to apply code changes: `docker-compose up --build`
