from flask import Flask, request, jsonify, Response
import threading
import time
import os
import requests
import ffmpeg
import json

app = Flask(__name__)

# Add CORS headers to all responses
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

app.after_request(add_cors_headers)

@app.route('/status/stream/<filename>', methods=['OPTIONS'])
def status_stream_options(filename):
    return add_cors_headers(Response())

# In-memory store for analysis results and progress
analysis_results = {}

@app.route('/notify', methods=['POST'])
def notify():
    data = request.get_json()
    # Extract bucket and key from S3 event
    try:
        record = data['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
    except Exception as e:
        return jsonify({'error': 'Invalid event format', 'details': str(e)}), 400

    # Start analysis in a background thread
    threading.Thread(target=analyze_file, args=(bucket, key)).start()
    return jsonify({'status': 'Analysis started', 'file': key})

@app.route('/status/<filename>', methods=['GET'])
def status(filename):
    result = analysis_results.get(filename)
    if not result:
        return jsonify({'status': 'pending'})
    return jsonify(result)

@app.route('/status/stream/<filename>')
def status_stream(filename):
    def event_stream():
        last_status = None
        while True:
            result = analysis_results.get(filename)
            if not result:
                status = 'pending'
            else:
                status = result.get('status')
            if status != last_status:
                last_status = status
                data = result if result else {'status': 'pending'}
                yield f"data: {json.dumps(data)}\n\n"
                if status in ('done', 'error'):
                    break
            time.sleep(1)
    response = Response(event_stream(), mimetype='text/event-stream')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

def analyze_file(bucket, key):
    filename = key.split('/')[-1]
    analysis_results[filename] = {'status': 'analyzing'}
    # Download file from S3 (LocalStack)
    s3_url = f"http://localstack:4566/{bucket}/{key}"
    local_path = f"/tmp/{filename}"
    try:
        r = requests.get(s3_url, stream=True)
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        # Analyze video duration
        probe = ffmpeg.probe(local_path)
        duration = float(probe['format']['duration'])
        analysis_results[filename] = {
            'status': 'done',
            'duration': duration
        }
    except Exception as e:
        analysis_results[filename] = {
            'status': 'error',
            'error': str(e)
        }
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 