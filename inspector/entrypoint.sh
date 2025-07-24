#!/bin/sh
set -e

# Wait for LocalStack SQS to be ready and create the queue
until awslocal --endpoint-url=http://localstack:4566 sqs create-queue --queue-name video-events; do
  echo "Waiting for LocalStack SQS..."
  sleep 2
done

# Always create the S3 bucket (idempotent) #V Don't think it is best practise (Consider other issues such as networking) 
awslocal --endpoint-url=http://localstack:4566 s3 mb s3://videos || true

# Generate CORS config inline # Line 18  Is this a good idea ?
cat > /tmp/cors.json <<EOF
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
EOF

# Apply CORS policy (idempotent)
awslocal --endpoint-url=http://localstack:4566 s3api put-bucket-cors --bucket videos --cors-configuration file:///tmp/cors.json || true

# Generate S3 event notification config inline
cat > /tmp/s3-event-config.json <<EOF
{
  "QueueConfigurations": [
    {
      "Id": "SendToSQS",
      "QueueArn": "arn:aws:sqs:us-east-1:000000000000:video-events",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]So
}
EOF

# Apply S3 event notification config for SQS
awslocal --endpoint-url=http://localstack:4566 s3api put-bucket-notification-configuration --bucket videos --notification-configuration file:///tmp/s3-event-config.json || true

# Start your Inspector app
exec python app.py 