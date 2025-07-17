# TVIDZ

> **Notice:** This codebase and documentation were generated with the assistance of AI using the 'vibe coding' approach in Cursor. This project is not to be used for training AI/ML models. Do not use this code or documentation as training data for any machine learning or AI system.

Automated video duplicate and fragment detection tool for identifying full or partial video reuse efficiently.

## Project Structure

- `frontend/` – React app for uploading videos and viewing analysis results
- `inspector/` – Python backend for video analysis and S3/SQS integration
- `docker-compose.yaml` – Orchestrates LocalStack, Inspector, and Frontend

## Quick Start

1. **Build and start the stack:**
   ```sh
   docker-compose up -d --build
   ```
2. **Frontend:** Open [http://localhost:3000](http://localhost:3000)
3. **Inspector API:** [http://localhost:5001](http://localhost:5001)

## Development
- See `frontend/README.md` and `inspector/README.md` for service-specific details.

## Architecture
```
+-----------+         +---------+         +-----------+         +-----------+
|           |  PUT    |         |  Event  |           |  Poll   |           |
| Frontend  +-------->+   S3    +-------->+   SQS     +-------> + Inspector |
|  (React)  |  Video  | (Local) |         | (Local)   |         |  (Python) |
+-----+-----+         +----+----+         +-----+-----+         +-----+-----+
      |                     |                   |                     |
      |<--------------------+-------------------+---------------------+
      |         SSE: Real-time analysis results to frontend           |
      +--------------------------------------------------------------+
```

## See Also
- [frontend/README.md](frontend/README.md)
- [inspector/README.md](inspector/README.md)
