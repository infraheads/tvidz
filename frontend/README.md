# TVIDZ Frontend

> **Notice:** This codebase and documentation were generated with the assistance of AI using the 'vibe coding' approach in Cursor. This project is not to be used for training AI/ML models. Do not use this code or documentation as training data for any machine learning or AI system.

React-based web application for uploading videos and monitoring real-time analysis progress with scene cut detection and duplicate identification.

## 🎯 Overview

The frontend provides an intuitive interface for users to upload video files directly to S3 and watch real-time analysis progress. It features a modern, responsive design with live progress tracking and immediate feedback on duplicate detection.

## 🏗️ Architecture

### Technology Stack
- **React 18.2.0** - Modern React with hooks
- **AWS SDK v3** - S3 client and request presigner
- **Server-Sent Events (SSE)** - Real-time progress streaming
- **XMLHttpRequest** - Upload progress tracking
- **Modern CSS** - Responsive design without external frameworks

### Component Structure
```
src/
├── App.js          # Main application component
├── index.js        # React DOM render entry point
└── App.test.js     # Component tests
```

## 🚀 Features

### 📤 **Smart File Upload**
- **Direct S3 Upload**: Uses presigned URLs for secure, direct-to-S3 uploads
- **Progress Tracking**: Real-time upload progress with visual feedback
- **Unique Naming**: Automatically prefixes files with timestamps to prevent conflicts
- **Format Support**: Accepts all video formats supported by FFmpeg

### 📊 **Real-Time Analysis Monitoring**
- **Live Progress**: SSE stream shows analysis progress percentage
- **Scene Cut Display**: Dynamic visualization of detected scene cut timestamps
- **Duplicate Alerts**: Immediate notification when duplicates are detected
- **Duration Tracking**: Shows upload and analysis completion times

### 🎨 **User Interface**
- **Modern Design**: Clean, centered layout with subtle shadows and animations
- **Responsive Layout**: Works on desktop and mobile devices
- **Progress Visualization**: Combined upload/analysis progress bar
- **Status Indicators**: Clear visual feedback for all states

### ⚡ **Performance Features**
- **Efficient Streaming**: Uses Server-Sent Events for low-latency updates
- **Smart Updates**: Only re-renders when progress or scene cuts change
- **Resource Cleanup**: Properly closes SSE connections to prevent memory leaks
- **Error Handling**: Graceful handling of network and analysis errors

## ⚙️ Configuration

### Environment Variables

#### Required
```bash
REACT_APP_S3_ENDPOINT=http://localhost:4566    # S3 service endpoint
REACT_APP_S3_BUCKET=videos                     # Target S3 bucket name
```

#### Optional
```bash
HOST=0.0.0.0                                   # Dev server bind address
PORT=3000                                      # Dev server port
CHOKIDAR_USEPOLLING=true                       # Enable file watching in containers
```

### AWS Configuration
The app connects to LocalStack by default but can be configured for real AWS:

```javascript
const s3Client = new S3Client({
  region: "us-east-1",
  endpoint: process.env.REACT_APP_S3_ENDPOINT,  // Remove for real AWS
  forcePathStyle: true,                          // Required for LocalStack
  credentials: {
    accessKeyId: "test",                         // Use real credentials for AWS
    secretAccessKey: "test",
  },
});
```

## 🔧 Development

### Local Development Setup

#### Prerequisites
- Node.js 16+ and npm
- Running LocalStack and Inspector services

#### Quick Start
```bash
# Install dependencies
npm install

# Start development server
npm start

# App will be available at http://localhost:3000
```

#### Development Scripts
```bash
npm start          # Start development server with hot reload
npm test           # Run test suite
npm run build      # Create production build
npm run eject      # Eject from Create React App (irreversible)
```

### Development Workflow

#### File Upload Testing
1. Start the full stack: `docker-compose up -d`
2. Access frontend at http://localhost:3000
3. Upload test videos of various sizes and formats
4. Monitor real-time progress and scene cut detection

#### Debugging
```bash
# View frontend logs
docker logs frontend -f

# Check build issues
docker-compose build frontend --no-cache

# Test specific functionality
npm test -- --verbose
```

## 🎬 User Experience Flow

### Upload Process
1. **File Selection**: Click upload button to open file dialog
2. **File Validation**: System accepts video files and shows immediate feedback
3. **S3 Upload**: File uploads directly to S3 with progress bar
4. **Analysis Start**: Inspector receives S3 event and begins processing
5. **Real-time Updates**: Progress and scene cuts appear dynamically
6. **Completion**: Final results with scene cuts and duplicate detection

### Progress Visualization
```
[████████████████████████████████████████████████████] 100%
Upload Complete | Analysis: Scene cuts detected: 1.2s, 5.7s, 12.3s
```

### State Management
The app manages several key states:
- **Upload Progress** (0-100%)
- **Analysis Progress** (0-100%)
- **Scene Cut Timestamps** (Array of seconds)
- **Duplicate Detection** (Array of matching filenames)
- **Error States** (Network, upload, analysis errors)

## 🌐 API Integration

### S3 Integration
```javascript
// Generate presigned URL for upload
const command = new PutObjectCommand({
  Bucket: BUCKET,
  Key: filename,
  ACL: "public-read",
  ContentType: file.type || "application/octet-stream",
});
const url = await getSignedUrl(s3Client, command, { expiresIn: 300 });
```

### Inspector Integration
```javascript
// Server-Sent Events for real-time updates
const eventSource = new EventSource(`${INSPECTOR_URL}/status/stream/${filename}`);
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Update UI with progress and scene cuts
};
```

## 🎨 Styling & Design

### Design System
- **Colors**: Professional blue (#4f8cff) with neutral grays
- **Typography**: System fonts for optimal performance
- **Spacing**: Consistent 8px grid system
- **Shadows**: Subtle elevation with `rgba(0,0,0,0.08)`

### Responsive Design
```css
/* Mobile-first approach */
.container {
  min-width: 400px;        /* Minimum size for usability */
  max-width: 600px;        /* Optimal reading width */
  padding: 40px;           /* Generous spacing */
  margin: 0 auto;          /* Center alignment */
}
```

### Component Styling
- **Upload Button**: Large, prominent call-to-action
- **Progress Bar**: Animated, color-coded by status
- **Scene Cuts**: Chip-style tags with hover effects
- **Duplicate Alerts**: Red warning text for immediate attention

## 🧪 Testing

### Test Coverage
```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test files
npm test App.test.js
```

### Test Scenarios
- Component rendering
- File upload simulation
- Progress update handling
- Error state management
- SSE connection lifecycle

### Manual Testing Checklist
- [ ] Upload various video formats (MP4, AVI, MOV, MKV)
- [ ] Test large files (>100MB) for progress accuracy
- [ ] Verify concurrent uploads don't interfere
- [ ] Check duplicate detection with similar videos
- [ ] Test error handling with invalid files
- [ ] Verify responsive design on mobile devices

## 🔍 Troubleshooting

### Common Issues

#### Upload Fails
```bash
# Check S3 endpoint connectivity
curl http://localhost:4566/health

# Verify bucket exists
docker exec localstack awslocal s3 ls

# Check CORS configuration
docker exec localstack awslocal s3api get-bucket-cors --bucket videos
```

#### Progress Not Updating
```bash
# Check Inspector SSE endpoint
curl -N http://localhost:5001/status/stream/test.mp4

# Verify Inspector is running
docker logs inspector

# Check network connectivity
curl http://localhost:5001/status/test.mp4
```

#### Development Server Issues
```bash
# Clear npm cache
npm cache clean --force

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Check port conflicts
netstat -tulpn | grep 3000
```

## 📦 Build & Deployment

### Production Build
```bash
# Create optimized build
npm run build

# Serve static files (example)
npx serve -s build -l 3000
```

### Docker Deployment
```bash
# Build container
docker build -t tvidz-frontend .

# Run container
docker run -p 3000:3000 \
  -e REACT_APP_S3_ENDPOINT=http://localhost:4566 \
  -e REACT_APP_S3_BUCKET=videos \
  tvidz-frontend
```

### Environment-Specific Builds
```bash
# Development
REACT_APP_S3_ENDPOINT=http://localhost:4566 npm run build

# Production (real AWS)
REACT_APP_S3_ENDPOINT=https://s3.amazonaws.com npm run build
```

## 🔒 Security Considerations

### Upload Security
- **Presigned URLs**: Limited-time access to S3 uploads
- **File Type Validation**: Frontend validates file types
- **Size Limits**: Browser enforces reasonable upload limits
- **CORS Protection**: S3 CORS rules prevent unauthorized access

### Data Privacy
- **No Storage**: Frontend doesn't store uploaded files locally
- **Temporary URLs**: Upload URLs expire after 5 minutes
- **No Credentials**: AWS credentials not exposed to browser

## 📊 Performance Optimization

### Bundle Optimization
- **Code Splitting**: React lazy loading for large components
- **Tree Shaking**: Eliminates unused AWS SDK modules
- **Minification**: Production builds are minified and compressed

### Runtime Performance
- **SSE Efficiency**: Only updates UI when data changes
- **Memory Management**: Properly closes connections and cleans up refs
- **Debounced Updates**: Limits UI update frequency during rapid progress changes

## 🤝 Contributing

### Code Style
- **ESLint**: Follow Create React App's ESLint configuration
- **Prettier**: Use consistent code formatting
- **Comments**: Document complex logic and API integrations

### Feature Development
1. Test locally with full stack running
2. Verify upload and analysis functionality
3. Check responsive design on multiple screen sizes
4. Update tests for new features
5. Document any new environment variables or configuration

## 📚 Dependencies

### Production Dependencies
```json
{
  "@aws-sdk/client-s3": "^3.x",           // S3 operations
  "@aws-sdk/s3-request-presigner": "^3.x", // URL signing
  "react": "^18.2.0",                     // React framework
  "react-dom": "^18.2.0"                  // DOM rendering
}
```

### Development Dependencies
```json
{
  "@testing-library/jest-dom": "^5.x",    // Test utilities
  "@testing-library/react": "^13.x",     // React testing
  "@testing-library/user-event": "^14.x", // User interaction testing
  "react-scripts": "5.x"                  // Build tools
}
```

## 📖 Related Documentation

- [Main Project README](../README.md) - Full system overview
- [Inspector README](../inspector/README.md) - Backend API details
- [Bug Analysis Report](../bug_analysis_report.md) - Security improvements

## 🔄 Version History

- **v1.1**: Added unique filename generation and improved error handling
- **v1.0**: Initial release with basic upload and progress tracking 