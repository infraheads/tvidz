#!/bin/sh
set -e

echo "Starting AWS LocalStack setup..."

# Function to check if LocalStack is ready
wait_for_localstack() {
    echo "Waiting for LocalStack to be ready..."
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if awslocal --endpoint-url=http://localstack:4566 sts get-caller-identity >/dev/null 2>&1; then
            echo "LocalStack is ready!"
            return 0
        fi
        echo "Attempt $attempt/$max_attempts: LocalStack not ready, waiting..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "ERROR: LocalStack failed to start after $max_attempts attempts"
    exit 1
}

# Function to create SQS queue with retry logic
create_sqs_queue() {
    echo "Creating SQS queue 'video-events'..."
    local max_attempts=10
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if awslocal --endpoint-url=http://localstack:4566 sqs create-queue --queue-name video-events >/dev/null 2>&1; then
            echo "SQS queue 'video-events' created successfully!"
            return 0
        fi
        echo "Attempt $attempt/$max_attempts: Failed to create SQS queue, retrying..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "ERROR: Failed to create SQS queue after $max_attempts attempts"
    exit 1
}

# Function to create S3 bucket
create_s3_bucket() {
    echo "Creating S3 bucket 'videos'..."
    if awslocal --endpoint-url=http://localstack:4566 s3 mb s3://videos >/dev/null 2>&1; then
        echo "S3 bucket 'videos' created successfully!"
    else
        echo "S3 bucket 'videos' already exists or creation failed (continuing...)"
    fi
}

# Function to configure CORS
configure_cors() {
    echo "Configuring CORS for S3 bucket..."
    cat > /tmp/cors.json <<EOF
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST", "HEAD", "DELETE"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "x-amz-request-id"],
      "MaxAgeSeconds": 3000
    }
  ]
}
EOF

    if awslocal --endpoint-url=http://localstack:4566 s3api put-bucket-cors --bucket videos --cors-configuration file:///tmp/cors.json >/dev/null 2>&1; then
        echo "CORS configuration applied successfully!"
    else
        echo "WARNING: Failed to apply CORS configuration"
    fi
}

# Function to configure S3 event notifications
configure_s3_events() {
    echo "Configuring S3 event notifications..."
    
    # Get the SQS queue ARN
    local queue_arn
    queue_arn=$(awslocal --endpoint-url=http://localstack:4566 sqs get-queue-attributes --queue-url http://localstack:4566/000000000000/video-events --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
    
    if [ -z "$queue_arn" ] || [ "$queue_arn" = "None" ]; then
        echo "ERROR: Failed to get SQS queue ARN"
        exit 1
    fi
    
    echo "Using SQS Queue ARN: $queue_arn"
    
    cat > /tmp/s3-event-config.json <<EOF
{
  "QueueConfigurations": [
    {
      "Id": "SendToSQS",
      "QueueArn": "$queue_arn",
      "Events": ["s3:ObjectCreated:*", "s3:ObjectCreated:Put", "s3:ObjectCreated:Post"]
    }
  ]
}
EOF

    if awslocal --endpoint-url=http://localstack:4566 s3api put-bucket-notification-configuration --bucket videos --notification-configuration file:///tmp/s3-event-config.json >/dev/null 2>&1; then
        echo "S3 event notifications configured successfully!"
    else
        echo "ERROR: Failed to configure S3 event notifications"
        exit 1
    fi
}

# Function to set SQS queue policy to allow S3 to send messages
configure_sqs_policy() {
    echo "Configuring SQS queue policy..."
    cat > /tmp/sqs-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:us-east-1:000000000000:video-events",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:s3:::videos"
        }
      }
    }
  ]
}
EOF

    local queue_url="http://localstack:4566/000000000000/video-events"
    if awslocal --endpoint-url=http://localstack:4566 sqs set-queue-attributes --queue-url "$queue_url" --attributes file:///tmp/sqs-policy.json >/dev/null 2>&1; then
        echo "SQS queue policy configured successfully!"
    else
        echo "WARNING: Failed to configure SQS queue policy"
    fi
}

# Function to verify the setup
verify_setup() {
    echo "Verifying AWS LocalStack setup..."
    
    # Check SQS queue
    if awslocal --endpoint-url=http://localstack:4566 sqs get-queue-url --queue-name video-events >/dev/null 2>&1; then
        echo "✓ SQS queue 'video-events' is accessible"
    else
        echo "✗ SQS queue 'video-events' is not accessible"
        exit 1
    fi
    
    # Check S3 bucket
    if awslocal --endpoint-url=http://localstack:4566 s3 ls s3://videos >/dev/null 2>&1; then
        echo "✓ S3 bucket 'videos' is accessible"
    else
        echo "✗ S3 bucket 'videos' is not accessible"
        exit 1
    fi
    
    echo "✓ AWS LocalStack setup verification completed successfully!"
}

# Main execution
echo "=== TVIDZ Inspector Initialization ==="

# Wait for LocalStack to be ready
wait_for_localstack

# Create and configure AWS resources
create_sqs_queue
create_s3_bucket
configure_cors
configure_sqs_policy
configure_s3_events

# Verify everything is working
verify_setup

echo "=== Starting Inspector Application ==="

# Start the Inspector app
exec python app.py 