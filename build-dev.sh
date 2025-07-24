#!/bin/bash

# Development build script for TVIDZ - builds and starts services

set -e

echo "🚀 TVIDZ Development Build & Start"
echo "================================="

# Get current timestamp
BUILD_DATE=$(date +"%Y-%m-%d")
BUILD_TIME=$(date +"%H:%M:%S %Z")

# Get git commit hash (short)
if git rev-parse --git-dir > /dev/null 2>&1; then
    GIT_COMMIT=$(git rev-parse --short HEAD)
    echo "📝 Git commit: $GIT_COMMIT"
else
    GIT_COMMIT="no-git"
    echo "⚠️  No git repository found, using 'no-git'"
fi

echo "📅 Build date: $BUILD_DATE"
echo "⏰ Build time: $BUILD_TIME"

# Export environment variables for docker-compose
export BUILD_DATE
export BUILD_TIME
export GIT_COMMIT

# Stop any running containers
echo "🛑 Stopping existing containers..."
docker-compose down

# Build and start services
echo "🏗️  Building and starting services..."
docker-compose up --build -d

echo ""
echo "✅ Build and deployment complete!"
echo ""
echo "📋 Build Information:"
echo "   Date: $BUILD_DATE"
echo "   Time: $BUILD_TIME"
echo "   Commit: $GIT_COMMIT"
echo ""
echo "🌐 Services are now running:"
echo "   Frontend: http://localhost:3000"
echo "   Inspector: http://localhost:5001"
echo "   Build Info: http://localhost:5001/build-info"
echo ""
echo "📊 To view logs:"
echo "   docker-compose logs -f"
echo ""
echo "🔧 To stop services:"
echo "   docker-compose down"
