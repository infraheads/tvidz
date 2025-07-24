#!/bin/bash

# Build script for TVIDZ with build timestamps and git info

set -e

echo "🏗️  Building TVIDZ with build information..."

# Get current timestamp
BUILD_DATE=$(date +"%Y-%m-%d")
BUILD_TIME=$(date +"%H:%M:%S %Z")

# Get git commit hash (short)
if git rev-parse --git-dir > /dev/null 2>&1; then
    GIT_COMMIT=$(git rev-parse --short HEAD)◊
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

# Build with docker-compose
echo "🐳 Building Docker containers..."
docker-compose build --no-cache

echo "✅ Build complete!"
echo ""
echo "📋 Build Information:"
echo "   Date: $BUILD_DATE"
echo "   Time: $BUILD_TIME"
echo "   Commit: $GIT_COMMIT"
echo ""
echo "🚀 To start the services:"
echo "   docker-compose up -d"
echo ""
echo "🌐 Services will be available at:"
echo "   Frontend: http://localhost:3000"
echo "   Inspector: http://localhost:5001"
echo "   Build Info: http://localhost:5001/build-info"
