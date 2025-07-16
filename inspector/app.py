from flask import Flask, request, jsonify, Response
import threading
import time
import os
import requests
import ffmpeg
import json
import boto3
import base64

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
    import time
    filename = key.split('/')[-1]
    analysis_results[filename] = {'status': 'analyzing', 'scene_cuts': [], 'progress': 0.0, 'total_cuts': 0}
    s3_url = f"http://localstack:4566/{bucket}/{key}"
    local_path = f"/tmp/{filename}"
    try:
        # Retry logic for download
        max_retries = 5
        total_frames = 0
        for attempt in range(max_retries):
            r = requests.get(s3_url, stream=True)
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            # Try probing the file to see if it's valid
            import ffmpeg
            try:
                probe = ffmpeg.probe(local_path)
                duration = float(probe['format']['duration'])
                # Get total frame count using ffprobe
                streams = probe.get('streams', [])
                video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
                if video_stream and 'nb_frames' in video_stream:
                    total_frames = int(video_stream['nb_frames'])
                else:
                    # fallback: use ffprobe to count frames
                    import subprocess
                    ffprobe_cmd = [
                        'ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                        '-show_entries', 'stream=nb_read_frames', '-of', 'default=nokey=1:noprint_wrappers=1', local_path
                    ]
                    ffprobe_out = subprocess.check_output(ffprobe_cmd, text=True).strip()
                    total_frames = int(ffprobe_out) if ffprobe_out.isdigit() else 0
                break  # Success
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    raise Exception(f"File download incomplete or corrupt after {max_retries} attempts: {e}")
        import subprocess
        # Get video duration for progress estimation (already set above)
        scene_cmd = [
            'ffmpeg', '-i', local_path,
            '-filter_complex', "select='gt(scene,0.3)',showinfo",
            '-f', 'null', '-'
        ]
        process = subprocess.Popen(scene_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        scene_timestamps = []
        last_progress = 0.0
        current_frame = 0
        for line in process.stderr:
            if 'showinfo' in line:
                # Parse frame number
                if 'n:' in line:
                    try:
                        n_part = line.split('n:')[1].split(' ')[0]
                        frame_num = int(n_part)
                        current_frame = frame_num
                    except Exception:
                        pass
                # Parse scene cut timestamp
                if 'pts_time:' in line:
                    parts = line.split('pts_time:')
                    if len(parts) > 1:
                        try:
                            ts = float(parts[1].split()[0])
                            scene_timestamps.append(ts)
                        except Exception:
                            pass
                # Update progress by frame
                if total_frames > 0 and current_frame > 0:
                    progress = min(current_frame / total_frames, 1.0)
                    if progress > last_progress or len(scene_timestamps) == 1:
                        last_progress = progress
                        analysis_results[filename] = {
                            'status': 'analyzing',
                            'scene_cuts': scene_timestamps.copy(),
                            'progress': progress,
                            'total_cuts': 0  # Will set at the end
                        }
        process.wait()
        analysis_results[filename] = {
            'status': 'done',
            'scene_cuts': scene_timestamps,
            'progress': 1.0,
            'total_cuts': len(scene_timestamps)
        }
    except Exception as e:
        analysis_results[filename] = {
            'status': 'error',
            'error': str(e),
            'progress': 0.0,
            'total_cuts': 0
        }
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

def poll_sqs():
    sqs = boto3.client(
        'sqs',
        region_name='us-east-1',
        endpoint_url='http://localstack:4566',
        aws_access_key_id='test',
        aws_secret_access_key='test',
    )
    queue_url = sqs.get_queue_url(QueueName='video-events')['QueueUrl']
    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10
        )
        messages = resp.get('Messages', [])
        for msg in messages:
            try:
                body = json.loads(msg['Body'])
                # S3 event notifications may be double-encoded
                if 'Message' in body:
                    body = json.loads(body['Message'])
                record = body['Records'][0]
                bucket = record['s3']['bucket']['name']
                key = record['s3']['object']['key']
                threading.Thread(target=analyze_file, args=(bucket, key)).start()
            except Exception as e:
                print(f"Error processing SQS message: {e}")
            finally:
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
        time.sleep(1)

if __name__ == '__main__':
    threading.Thread(target=poll_sqs, daemon=True).start()
    app.run(host='0.0.0.0', port=5000) 