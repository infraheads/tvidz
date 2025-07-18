from flask import Flask, request, jsonify, Response
import threading
import time
import os
import requests
import ffmpeg
import json
import boto3
import base64
import copy
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

# In-memory store for analysis results and progress with proper thread safety
analysis_results = {}
analysis_lock = threading.RLock()  # Use RLock for nested locking scenarios

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
        # Return a deep copy to prevent race conditions
        if not result:
            print(f"[status] No result in memory for {filename}")
            return jsonify({'status': 'pending'})
        print(f"[status] Serving result from memory for {filename}")
        return jsonify(copy.deepcopy(result))

@app.route('/status/stream/<filename>')
def status_stream(filename):
    def event_stream():
        last_status = None
        last_progress = None
        last_scene_cuts_len = None
        while True:
            with analysis_lock:
                result = analysis_results.get(filename)
                # Create a deep copy to prevent modification during iteration
                result_copy = copy.deepcopy(result) if result else None
                
            if not result_copy:
                status = 'pending'
                progress = 0.0
                scene_cuts_len = 0
            else:
                status = result_copy.get('status')
                progress = result_copy.get('progress', 0.0)
                scene_cuts_len = len(result_copy.get('scene_cuts', []))
                
            # Yield if any of the tracked fields change
            if (
                status != last_status or
                progress != last_progress or
                scene_cuts_len != last_scene_cuts_len
            ):
                last_status = status
                last_progress = progress
                last_scene_cuts_len = scene_cuts_len
                data = result_copy if result_copy else {'status': 'pending'}
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
    import signal
    filename = key.split('/')[-1]
    local_path = f"/tmp/{filename}"
    process = None
    
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
    try:
        video = add_video(filename)
        video_id = video.id
    except Exception as e:
        print(f"[error] Failed to add video to database: {e}")
        with analysis_lock:
            analysis_results[filename] = {
                'status': 'error',
                'error': f'Database error: {str(e)}',
                'progress': 0.0,
                'total_cuts': 0,
                'duplicates': []
            }
        return
    
    with analysis_lock:
        analysis_results[filename] = {'status': 'analyzing', 'scene_cuts': [], 'progress': 0.0, 'total_cuts': 0, 'duplicates': []}
    s3_url = f"http://localstack:4566/{bucket}/{key}"
    
    try:
        # Retry logic for download with better error handling
        max_retries = 5
        total_frames = 0
        for attempt in range(max_retries):
            try:
                r = requests.get(s3_url, stream=True, timeout=30)
                r.raise_for_status()
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
                # Try probing the file to see if it's valid
                try:
                    probe = ffmpeg.probe(local_path)
                    streams = probe.get('streams', [])
                    video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
                    if video_stream and 'nb_frames' in video_stream:
                        total_frames = int(video_stream['nb_frames'])
                    else:
                        # fallback: use ffprobe to count frames with timeout
                        ffprobe_cmd = [
                            'timeout', '60',  # 60 second timeout
                            'ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                            '-show_entries', 'stream=nb_read_frames', '-of', 'default=nokey=1:noprint_wrappers=1', local_path
                        ]
                        ffprobe_out = subprocess.check_output(ffprobe_cmd, text=True, timeout=65).strip()
                        total_frames = int(ffprobe_out) if ffprobe_out.isdigit() else 0
                    break  # Success
                except subprocess.TimeoutExpired:
                    raise Exception("FFprobe timeout - file may be too large or corrupted")
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"[retry] Attempt {attempt + 1} failed: {e}")
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        raise Exception(f"File probe failed after {max_retries} attempts: {e}")
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[retry] Download attempt {attempt + 1} failed: {e}")
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    raise Exception(f"File download failed after {max_retries} attempts: {e}")
        
        # Run ffmpeg for scene cut detection and progress in one process with timeout
        scene_cmd = [
            'timeout', '300',  # 5 minute timeout for analysis
            'stdbuf', '-oL', '-eL',
            'ffmpeg', '-hide_banner', '-loglevel', 'info',
            '-i', local_path,
            '-vf', 'select=gt(scene\,0.8),showinfo',
            '-f', 'null', '-'
        ]
        
        try:
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
                        except (ValueError, IndexError):
                            pass
                    # Parse scene cut timestamp
                    if 'pts_time:' in line:
                        try:
                            ts = float(line.split('pts_time:')[1].split()[0])
                            if not scene_timestamps or ts != scene_timestamps[-1]:
                                scene_timestamps.append(ts)
                                # Incremental DB update and duplicate search
                                try:
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
                                except Exception as e:
                                    print(f"[error] Database operation failed: {e}")
                        except (ValueError, IndexError):
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
                        if filename in analysis_results:  # Check if still exists
                            analysis_results[filename]['progress'] = progress
                            analysis_results[filename]['scene_cuts'] = scene_timestamps.copy()
                if duplicate_found:
                    print(f"[progress-update-before-break] {filename}: {progress*100:.2f}% ({current_frame}/{total_frames})")
                    with analysis_lock:
                        if filename in analysis_results:  # Check if still exists
                            analysis_results[filename]['progress'] = progress
                            analysis_results[filename]['scene_cuts'] = scene_timestamps.copy()
                    break
                    
            # Wait for process to complete
            return_code = process.wait()
            if return_code != 0 and return_code != 124:  # 124 is timeout return code
                raise Exception(f"FFmpeg process failed with return code {return_code}")
                
        except subprocess.TimeoutExpired:
            if process:
                process.kill()
                process.wait()
            raise Exception("Analysis timeout - video processing took too long")
        finally:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        
        with analysis_lock:
            if filename in analysis_results:  # Check if still exists
                analysis_results[filename] = {
                    'status': 'done',
                    'scene_cuts': scene_timestamps,
                    'progress': 1.0,
                    'total_cuts': len(scene_timestamps),
                    'duplicates': list(set(dups_to_report)) if dups_to_report else []
                }
    except Exception as e:
        print(f"[error] Analysis failed for {filename}: {e}")
        with analysis_lock:
            analysis_results[filename] = {
                'status': 'error',
                'error': str(e),
                'progress': 0.0,
                'total_cuts': 0,
                'duplicates': []
            }
    finally:
        # Cleanup: Kill any remaining process
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            except Exception as e:
                print(f"[cleanup] Failed to terminate process: {e}")
                
        # Cleanup: Remove temporary file
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
    import logging
    
    # Configure logging for SQS polling
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('sqs_poller')
    
    sqs = boto3.client(
        'sqs',
        region_name='us-east-1',
        endpoint_url='http://localstack:4566',
        aws_access_key_id='test',
        aws_secret_access_key='test',
    )
    
    queue_url = None
    max_connection_attempts = 20
    
    # Wait for SQS queue to be available with exponential backoff
    for attempt in range(max_connection_attempts):
        try:
            response = sqs.get_queue_url(QueueName='video-events')
            queue_url = response['QueueUrl']
            logger.info(f"Successfully connected to SQS queue: {queue_url}")
            break
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'QueueDoesNotExist':
                logger.warning(f"Queue does not exist yet (attempt {attempt+1}/{max_connection_attempts})")
            else:
                logger.error(f"SQS connection error: {e}")
            
            # Exponential backoff with jitter
            sleep_time = min(60, (2 ** attempt) + (attempt * 0.1))
            time.sleep(sleep_time)
        except Exception as e:
            logger.error(f"Unexpected error connecting to SQS: {e}")
            time.sleep(5)
    
    if not queue_url:
        logger.error("Failed to get SQS queue URL after multiple attempts. SQS polling disabled.")
        return
    
    logger.info("Starting SQS message polling...")
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while True:
        try:
            # Poll for messages with longer wait time for efficiency
            resp = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,  # Process up to 10 messages at once
                WaitTimeSeconds=20,      # Long polling for efficiency
                MessageAttributeNames=['All'],
                AttributeNames=['All']
            )
            
            messages = resp.get('Messages', [])
            if not messages:
                # Reset error counter on successful poll (even if no messages)
                consecutive_errors = 0
                continue
                
            logger.info(f"Received {len(messages)} message(s) from SQS")
            
            for msg in messages:
                try:
                    # Parse message body
                    body = msg.get('Body', '{}')
                    try:
                        parsed_body = json.loads(body)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse message body as JSON: {e}")
                        # Delete malformed message
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
                        continue
                    
                    # Handle S3 event notifications (may be double-encoded)
                    if 'Message' in parsed_body:
                        try:
                            parsed_body = json.loads(parsed_body['Message'])
                        except json.JSONDecodeError:
                            pass  # If it fails, use the original parsed_body
                    
                    # Extract S3 event information
                    if 'Records' not in parsed_body:
                        logger.warning(f"Message does not contain 'Records' field: {parsed_body}")
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
                        continue
                    
                    for record in parsed_body.get('Records', []):
                        try:
                            # Validate record structure
                            if 's3' not in record:
                                logger.warning(f"Record missing 's3' field: {record}")
                                continue
                                
                            s3_info = record['s3']
                            if 'bucket' not in s3_info or 'object' not in s3_info:
                                logger.warning(f"S3 record missing bucket or object info: {s3_info}")
                                continue
                                
                            bucket = s3_info['bucket']['name']
                            key = s3_info['object']['key']
                            event_name = record.get('eventName', 'Unknown')
                            
                            logger.info(f"Processing S3 event: {event_name} for {bucket}/{key}")
                            
                            # Only process object creation events
                            if not event_name.startswith('s3:ObjectCreated:'):
                                logger.info(f"Ignoring non-creation event: {event_name}")
                                continue
                            
                            # Start analysis in background thread
                            thread = threading.Thread(
                                target=analyze_file, 
                                args=(bucket, key),
                                name=f"analyzer-{key}"
                            )
                            thread.daemon = True
                            thread.start()
                            
                            logger.info(f"Started analysis thread for {bucket}/{key}")
                            
                        except Exception as e:
                            logger.error(f"Error processing S3 record: {e}, record: {record}")
                            
                except Exception as e:
                    logger.error(f"Error processing SQS message: {e}, message: {msg}")
                finally:
                    # Always delete the message to prevent reprocessing
                    try:
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
                        logger.debug(f"Deleted message: {msg.get('MessageId', 'unknown')}")
                    except Exception as e:
                        logger.error(f"Failed to delete message: {e}")
            
            # Reset error counter on successful processing
            consecutive_errors = 0
            
        except botocore.exceptions.ClientError as e:
            consecutive_errors += 1
            error_code = e.response['Error']['Code']
            logger.error(f"SQS client error ({consecutive_errors}/{max_consecutive_errors}): {error_code} - {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Too many consecutive SQS errors. Stopping SQS polling.")
                break
                
            # Exponential backoff for client errors
            sleep_time = min(60, 2 ** min(consecutive_errors, 6))
            time.sleep(sleep_time)
            
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Unexpected SQS polling error ({consecutive_errors}/{max_consecutive_errors}): {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Too many consecutive SQS errors. Stopping SQS polling.")
                break
                
            time.sleep(5)  # Brief pause before retrying

if __name__ == '__main__':
    threading.Thread(target=poll_sqs, daemon=True).start()
    app.run(host='0.0.0.0', port=5000) 