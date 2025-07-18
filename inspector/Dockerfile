FROM python:3.11-slim

WORKDIR /app

# Capture build timestamp
ARG BUILD_DATE
ARG BUILD_TIME
ARG GIT_COMMIT
ENV BUILD_DATE=${BUILD_DATE}
ENV BUILD_TIME=${BUILD_TIME}
ENV GIT_COMMIT=${GIT_COMMIT}

RUN apt-get update && apt-get install -y ffmpeg libssl-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install awscli and awscli-local for interacting with LocalStack
RUN pip install awscli
RUN pip install awscli-local

# Install Python linters
RUN pip install ruff flake8

ENV PYTHONUNBUFFERED=1

COPY . .

# Copy entrypoint script and make it executable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"] 