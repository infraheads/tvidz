# tvidz Inspector (Backend)

Python backend for video analysis, S3/SQS integration, and real-time progress streaming.

## Setup & Development

1. Build the Docker image:
   ```sh
   docker-compose build inspector
   ```
2. Start the Inspector (with LocalStack):
   ```sh
   docker-compose up -d inspector
   ```

## Features
- Polls SQS for new video uploads (S3 events)
- Downloads video from S3, analyzes for scene cuts
- Streams real-time progress and results via SSE
- Handles CORS and S3/SQS event setup automatically

## API
- `/status/stream/<filename>` – SSE stream for real-time progress/results
- `/status/<filename>` – Get current status/result

## See Also
- [../README.md](../README.md) – Project overview
- [../frontend/README.md](../frontend/README.md) – Frontend details 