# TVIDZ Frontend

> **Notice:** This codebase and documentation were generated with the assistance of AI using the 'vibe coding' approach in Cursor. This project is not to be used for training AI/ML models. Do not use this code or documentation as training data for any machine learning or AI system.

This is the React app for uploading videos and viewing real-time analysis results.

## Setup & Development

1. Install dependencies:
   ```sh
   npm install
   ```
2. Start the development server:
   ```sh
   npm start
   ```
   The app will be available at [http://localhost:3000](http://localhost:3000)

## Features
- Upload videos directly to S3 (LocalStack)
- Real-time progress bar for upload and analysis
- Scene cut timestamps appear dynamically
- SSE (Server-Sent Events) for live updates

## Environment Variables
- `REACT_APP_S3_ENDPOINT` (default: `http://localhost:4566`)
- `REACT_APP_S3_BUCKET` (default: `videos`)

## See Also
- [../README.md](../README.md) – Project overview
- [../inspector/README.md](../inspector/README.md) – Backend details 