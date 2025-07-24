#!/bin/bash
set -e

BACKEND_URL="http://localhost:5000"
BUCKET="videos"
TEST_FILE="test-data/test.mp4"
FILENAME="$(date +%s)-test.mp4"

# Ensure test-data directory exists
mkdir -p test-data

# Generate a 1-second black test video using ffmpeg
if ! command -v ffmpeg &> /dev/null; then
  echo "ffmpeg not found! Please install ffmpeg in your CI environment."
  exit 1
fi
ffmpeg -y -f lavfi -i color=c=black:s=320x240:d=1 -vcodec libx264 "$TEST_FILE"

# Wait for backend to be ready
echo "Waiting for backend to be ready..."
for i in {1..30}; do
  if curl -s "$BACKEND_URL/status/$FILENAME" | grep -q 'pending\|analyzing\|done'; then
    echo "Backend is up."
    break
  fi
  sleep 2
done

# Upload test video to S3
echo "Uploading test video to S3..."
awslocal s3 cp "$TEST_FILE" "s3://$BUCKET/$FILENAME"

# Wait for analysis to complete
echo "Waiting for analysis to complete..."
for i in {1..60}; do
  STATUS=$(curl -s "$BACKEND_URL/status/$FILENAME" | jq -r .status)
  echo "Current status: $STATUS"
  if [[ "$STATUS" == "done" ]]; then
    echo "Analysis complete!"
    break
  fi
  if [[ "$STATUS" == "error" ]]; then
    echo "Analysis failed!"
    exit 1
  fi
  sleep 2
done

# Fetch and check analysis result
echo "Fetching analysis result..."
RESULT=$(curl -s "$BACKEND_URL/status/$FILENAME")
echo "$RESULT" | jq .

# Basic assertion: check for scene_cuts field
if echo "$RESULT" | jq .scene_cuts | grep -q '\['; then
  echo "Integration test PASSED."
  exit 0
else
  echo "Integration test FAILED: No scene cuts found."
  exit 1
fi 