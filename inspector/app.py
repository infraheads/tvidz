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
        # Look for results by original filename across all analysis keys
        result = None
        for key, data in analysis_results.items():
            if data.get('original_filename') == filename:
                result = data
                break
        # Fallback to direct lookup for backward compatibility
        if not result:
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
        last_duplicates_len = None
        while True:
            with analysis_lock:
                # Look for results by original filename across all analysis keys
                result = None
                for key, data in analysis_results.items():
                    if data.get('original_filename') == filename:
                        result = data
                        break
                # Fallback to direct lookup for backward compatibility
                if not result:
                    result = analysis_results.get(filename)
            if not result:
                status = 'pending'
                progress = 0.0
                scene_cuts_len = 0
                duplicates_len = 0
            else:
                status = result.get('status')
                progress = result.get('progress', 0.0)
                scene_cuts_len = len(result.get('scene_cuts', []))
                duplicates_len = len(result.get('duplicates', []))
            # Yield if any of the tracked fields change (more sensitive to progress changes)
            progress_changed = last_progress is None or abs(progress - last_progress) >= 0.01  # 1% change threshold
            if (
                status != last_status or
                progress_changed or
                scene_cuts_len != last_scene_cuts_len or
                duplicates_len != last_duplicates_len
            ):
                last_status = status
                last_progress = progress
                last_scene_cuts_len = scene_cuts_len
                last_duplicates_len = duplicates_len
                data = result if result else {'status': 'pending'}
                yield f"data: {json.dumps(data)}\n\n"
                if status in ('done', 'error'):
                    break
            time.sleep(0.2)  # More frequent updates
    response = Response(event_stream(), mimetype='text/event-stream')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

def analyze_file(bucket, key):
    import time
    import subprocess
    import uuid
    # Extract filename safely from S3 key
    filename = key.split('/')[-1] if key and '/' in key else key or 'unknown_file'
    if not filename:
        filename = 'unknown_file'
    # Create a unique identifier to prevent race conditions with same filename
    unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    local_path = f"/tmp/{unique_id}_{filename}"
    analysis_key = f"{unique_id}_{filename}"
    
    # Ensure no stale result or file for this specific analysis
    with analysis_lock:
        if analysis_key in analysis_results:
            del analysis_results[analysis_key]
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
        analysis_results[analysis_key] = {
            'status': 'analyzing', 
            'scene_cuts': [], 
            'progress': 0.0, 
            'total_cuts': 0, 
            'duplicates': [], 
            'original_filename': filename
        }
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
        # Validate local_path to prevent command injection
        if not os.path.exists(local_path) or not local_path.startswith('/tmp/'):
            raise Exception(f"Invalid or unsafe file path: {local_path}")
        
        scene_cmd = [
            'stdbuf', '-oL', '-eL',
            'ffmpeg', '-hide_banner', '-loglevel', 'info',
            '-i', local_path,
            '-vf', 'select=gt(scene\\,0.3),showinfo',  # Lower threshold for more scene cuts
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
                            dups = find_duplicates(scene_timestamps, min_match=2)  # Lower threshold for better detection
                            # Remove self from duplicates
                            dups = [d for d in dups if d[0] != video_id]
                            if dups and not duplicate_found:
                                update_duplicates(video_id, [d[0] for d in dups])
                                dups_to_report = []
                                for dup_id, match_count in dups:
                                    dup_video = get_video_by_id(dup_id)
                                    if dup_video:
                                        dups_to_report.append(dup_video.filename)
                                        print(f"[duplicate] Match found: {dup_video.filename} ({match_count} matching timestamps)")
                                duplicate_found = True
                                print(f"[duplicate] Found {len(dups_to_report)} duplicates: {dups_to_report}")
                                print(f"[duplicate] Current scene cuts: {scene_timestamps}")
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
                len(scene_timestamps) > len(analysis_results[analysis_key]['scene_cuts'])
            ):
                last_progress = progress
                last_update_time = now
                print(f"[progress-update] {filename}: {progress*100:.2f}% ({current_frame}/{total_frames})")
                with analysis_lock:
                    analysis_results[analysis_key]['progress'] = progress
                    analysis_results[analysis_key]['scene_cuts'] = scene_timestamps.copy()
                    # Update duplicates in real-time if found
                    if dups_to_report:
                        analysis_results[analysis_key]['duplicates'] = list(set(dups_to_report))
            if duplicate_found:
                print(f"[progress-update-before-break] {filename}: {progress*100:.2f}% ({current_frame}/{total_frames})")
                with analysis_lock:
                    analysis_results[analysis_key]['progress'] = progress
                    analysis_results[analysis_key]['scene_cuts'] = scene_timestamps.copy()
                    # Update duplicates before breaking
                    if dups_to_report:
                        analysis_results[analysis_key]['duplicates'] = list(set(dups_to_report))
                break
        process.wait()
        with analysis_lock:
            analysis_results[analysis_key] = {
                'status': 'done',
                'scene_cuts': scene_timestamps,
                'progress': 1.0,
                'total_cuts': len(scene_timestamps),
                'duplicates': list(set(dups_to_report)) if dups_to_report else [],
                'original_filename': filename
            }
    except Exception as e:
        with analysis_lock:
            # Preserve any duplicates found before the error
            existing_duplicates = analysis_results.get(analysis_key, {}).get('duplicates', [])
            analysis_results[analysis_key] = {
                'status': 'error',
                'error': str(e),
                'progress': 0.0,
                'total_cuts': 0,
                'duplicates': existing_duplicates,
                'original_filename': filename
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

@app.route('/build-info', methods=['GET'])
def build_info():
    """Return build information for both frontend and inspector"""
    return jsonify({
        'inspector': {
            'build_date': os.environ.get('BUILD_DATE', 'unknown'),
            'build_time': os.environ.get('BUILD_TIME', 'unknown'),
            'git_commit': os.environ.get('GIT_COMMIT', 'unknown'),
            'service': 'inspector'
        }
    })

@app.route('/debug/videos', methods=['GET'])
def debug_videos():
    """Debug endpoint to see all videos and their timestamps"""
    from db import SessionLocal, Video, VideoTimestamps
    session = SessionLocal()
    try:
        videos = session.query(Video).all()
        result = []
        for video in videos:
            timestamps = session.query(VideoTimestamps).filter_by(video_id=video.id).first()
            result.append({
                'id': video.id,
                'filename': video.filename,
                'upload_time': video.upload_time.isoformat() if video.upload_time else None,
                'duplicates': video.duplicates,
                'timestamps': timestamps.timestamps if timestamps else []
            })
        return jsonify({'videos': result, 'count': len(result)})
    finally:
        session.close()

@app.route('/debug/create-test-video', methods=['POST'])
def create_test_video():
    """Create a test video with predefined timestamps for duplicate testing"""
    test_filename = request.json.get('filename', 'test_video.mp4')
    test_timestamps = request.json.get('timestamps', [1.2, 5.7, 12.3, 18.9, 25.1])
    
    try:
        video = add_video(test_filename)
        add_timestamps(video.id, test_timestamps)
        return jsonify({
            'status': 'created',
            'video_id': video.id,
            'filename': test_filename,
            'timestamps': test_timestamps
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            print(f"[poll_sqs] Successfully got queue URL: {queue_url}")
            break
        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            # Automatically create the queue when it does not exist yet
            if error_code == 'AWS.SimpleQueueService.NonExistentQueue':
                print("[poll_sqs] Queue does not exist. Creating 'video-events' queue...")
                try:
                    sqs.create_queue(QueueName='video-events')
                    print("[poll_sqs] Queue created successfully. Waiting for it to be ready...")
                    time.sleep(2)  # Give LocalStack time to initialize the queue
                    # Try to get the URL immediately after creation
                    queue_url = sqs.get_queue_url(QueueName='video-events')['QueueUrl']
                    print(f"[poll_sqs] Successfully got queue URL after creation: {queue_url}")
                    break
                except Exception as create_error:
                    print(f"[poll_sqs] Error creating queue: {create_error}")
                    time.sleep(2)
            else:
                print(f"[poll_sqs] Waiting for SQS queue to be available... (attempt {attempt+1}, error: {error_code})")
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