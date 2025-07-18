from flask import Flask, request, jsonify, Response
import threading
import time
import os
import requests
import ffmpeg
import json
import boto3
import base64
from db import add_video, add_timestamps, update_duplicates, find_duplicates, get_video_by_filename, get_video_by_id

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
analysis_lock = threading.Lock()

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
    with analysis_lock:
        result = analysis_results.get(filename)
    if not result:
        print(f"[status] No result in memory for {filename}")
        return jsonify({'status': 'pending'})
    print(f"[status] Serving result from memory for {filename}")
    return jsonify(result)

@app.route('/status/stream/<filename>')
def status_stream(filename):
    def event_stream():
        last_status = None
        last_progress = None
        last_scene_cuts_len = None
        while True:
            with analysis_lock:
                result = analysis_results.get(filename)
            if not result:
                status = 'pending'
                progress = 0.0
                scene_cuts_len = 0
            else:
                status = result.get('status')
                progress = result.get('progress', 0.0)
                scene_cuts_len = len(result.get('scene_cuts', []))
            # Yield if any of the tracked fields change
            if (
                status != last_status or
                progress != last_progress or
                scene_cuts_len != last_scene_cuts_len
            ):
                last_status = status
                last_progress = progress
                last_scene_cuts_len = scene_cuts_len
                data = result if result else {'status': 'pending'}
                yield f"data: {json.dumps(data)}\n\n"
                if status in ('done', 'error'):
                    break
            time.sleep(0.5)
    response = Response(event_stream(), mimetype='text/event-stream')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

def analyze_file(bucket, key):
    import time
    import subprocess
    filename = key.split('/')[-1]
    local_path = f"/tmp/{filename}"
    # Ensure no stale result or file
    with analysis_lock:
        if filename in analysis_results:
            del analysis_results[filename]
    if os.path.exists(local_path):
        try:
            os.remove(local_path)
            print(f"[cleanup] Removed stale file: {local_path}")
        except Exception as e:
            print(f"[cleanup] Failed to remove stale file: {local_path} ({e})")
    print(f"[analysis-triggered] Starting analysis for {filename}")
    # Add video metadata to DB
    video = add_video(filename)
    video_id = video.id
    with analysis_lock:
        analysis_results[filename] = {'status': 'analyzing', 'scene_cuts': [], 'progress': 0.0, 'total_cuts': 0, 'duplicates': []}
    s3_url = f"http://localstack:4566/{bucket}/{key}"
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
                streams = probe.get('streams', [])
                video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
                if video_stream and 'nb_frames' in video_stream:
                    total_frames = int(video_stream['nb_frames'])
                else:
                    # fallback: use ffprobe to count frames
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
        # Run ffmpeg for scene cut detection and progress in one process
        scene_cmd = [
            'stdbuf', '-oL', '-eL',
            'ffmpeg', '-hide_banner', '-loglevel', 'info',
            '-i', local_path,
            '-vf', 'select=gt(scene\,0.8),showinfo',
            '-f', 'null', '-'
        ]
        process = subprocess.Popen(scene_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        scene_timestamps = []
        current_frame = 0
        last_progress = 0.0
        last_update_time = time.time()
        duplicate_found = False
        dups_to_report = []
        for line in process.stderr:
            now = time.time()
            line = line.strip()
            if 'showinfo' in line:
                # Parse frame number
                if 'n:' in line:
                    try:
                        n_part = line.split('n:')[1].split(' ')[0]
                        current_frame = int(n_part)
                    except Exception:
                        pass
                # Parse scene cut timestamp
                if 'pts_time:' in line:
                    try:
                        ts = float(line.split('pts_time:')[1].split()[0])
                        if not scene_timestamps or ts != scene_timestamps[-1]:
                            scene_timestamps.append(ts)
                            # Incremental DB update and duplicate search
                            add_timestamps(video_id, scene_timestamps)
                            dups = find_duplicates(scene_timestamps, min_match=3)
                            # Remove self from duplicates
                            dups = [d for d in dups if d[0] != video_id]
                            if dups and not duplicate_found:
                                update_duplicates(video_id, [d[0] for d in dups])
                                dups_to_report = [get_video_by_id(d[0]).filename for d in dups]
                                duplicate_found = True
                                print(f"[duplicate] Found duplicates: {dups}, stopping analysis early.")
                                break
                    except Exception:
                        pass
            # Update progress and scene cuts incrementally
            if total_frames > 0 and current_frame > 0:
                progress = min(current_frame / total_frames, 1.0)
            else:
                progress = 0.0
            if (
                progress > last_progress or
                now - last_update_time > 0.5 or
                len(scene_timestamps) > len(analysis_results[filename]['scene_cuts'])
            ):
                last_progress = progress
                last_update_time = now
                print(f"[progress-update] {filename}: {progress*100:.2f}% ({current_frame}/{total_frames})")
                with analysis_lock:
                    analysis_results[filename]['progress'] = progress
                    analysis_results[filename]['scene_cuts'] = scene_timestamps.copy()
            if duplicate_found:
                print(f"[progress-update-before-break] {filename}: {progress*100:.2f}% ({current_frame}/{total_frames})")
                with analysis_lock:
                    analysis_results[filename]['progress'] = progress
                    analysis_results[filename]['scene_cuts'] = scene_timestamps.copy()
                break
        process.wait()
        with analysis_lock:
            analysis_results[filename] = {
                'status': 'done',
                'scene_cuts': scene_timestamps,
                'progress': 1.0,
                'total_cuts': len(scene_timestamps),
                'duplicates': list(set(dups_to_report)) if dups_to_report else []
            }
    except Exception as e:
        with analysis_lock:
            analysis_results[filename] = {
                'status': 'error',
                'error': str(e),
                'progress': 0.0,
                'total_cuts': 0,
                'duplicates': []
            }
    finally:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                print(f"[cleanup] Removed file: {local_path}")
            except Exception as e:
                print(f"[cleanup] Failed to remove file: {local_path} ({e})")

# Utility to clear the database (for development/testing)
@app.route('/admin/clear-db', methods=['POST'])
def clear_db():
    from db import SessionLocal, Video, VideoTimestamps
    session = SessionLocal()
    session.query(VideoTimestamps).delete()
    session.query(Video).delete()
    session.commit()
    session.close()
    return jsonify({'status': 'cleared'})

def poll_sqs():
    import botocore
    sqs = boto3.client(
        'sqs',
        region_name='us-east-1',
        endpoint_url='http://localstack:4566',
        aws_access_key_id='test',
        aws_secret_access_key='test',
    )
    queue_url = None
    # Attempt to fetch the queue URL; create the queue if it is missing.
    for attempt in range(10):
        try:
            queue_url = sqs.get_queue_url(QueueName='video-events')['QueueUrl']
            break
        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            # Automatically create the queue when it does not exist yet
            if error_code == 'AWS.SimpleQueueService.NonExistentQueue':
                print("[poll_sqs] Queue does not exist. Creating 'video-events' queue...")
                sqs.create_queue(QueueName='video-events')
            else:
                print(f"Waiting for SQS queue to be available... (attempt {attempt+1})")
                time.sleep(2)
    if not queue_url:
        print("Failed to get SQS queue URL after multiple attempts.")
        return
    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10
        )
        messages = resp.get('Messages', [])
        for msg in messages:
            processed_successfully = False
            try:
                body = json.loads(msg['Body'])
                # S3 event notifications may be double-encoded
                if 'Message' in body:
                    body = json.loads(body['Message'])
                record = body['Records'][0]
                bucket = record['s3']['bucket']['name']
                key = record['s3']['object']['key']
                threading.Thread(target=analyze_file, args=(bucket, key)).start()
                processed_successfully = True
            except Exception as e:
                print(f"Error processing SQS message: {e}")
            finally:
                # Only delete the message if it has been handled successfully to avoid data loss.
                if processed_successfully:
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
        time.sleep(1)

if __name__ == '__main__':
    threading.Thread(target=poll_sqs, daemon=True).start()
    app.run(host='0.0.0.0', port=5000) 