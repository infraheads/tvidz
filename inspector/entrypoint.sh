#!/bin/sh
set -e

# Wait for LocalStack SQS to be ready and create the queue
until awslocal --endpoint-url=http://localstack:4566 sqs create-queue --queue-name video-events; do
  echo "Waiting for LocalStack SQS..."
  sleep 2
done

# Always create the S3 bucket (idempotent)
awslocal --endpoint-url=http://localstack:4566 s3 mb s3://videos || true

# Copy CORS config into the container if not present
if [ ! -f /tmp/cors.json ]; then
  cp /app/../cors.json /tmp/cors.json || cp /app/cors.json /tmp/cors.json || true
fi

# Apply CORS policy (idempotent)
awslocal --endpoint-url=http://localstack:4566 s3api put-bucket-cors --bucket videos --cors-configuration file:///tmp/cors.json || true

# Apply S3 event notification config for SQS
awslocal --endpoint-url=http://localstack:4566 s3api put-bucket-notification-configuration --bucket videos --notification-configuration file:///app/../s3-event-config.json || awslocal --endpoint-url=http://localstack:4566 s3api put-bucket-notification-configuration --bucket videos --notification-configuration file:///app/s3-event-config.json || true

# Start your Inspector app
exec python app.py 