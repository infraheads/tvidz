import pytest
import json
from app import app, analysis_results

def test_status_pending():
    client = app.test_client()
    resp = client.get('/status/nonexistentfile.mp4')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'pending'

def test_status_stream_options():
    client = app.test_client()
    resp = client.options('/status/stream/somefile.mp4')
    assert resp.status_code == 200
    assert resp.headers['Access-Control-Allow-Origin'] == '*'

def test_notify_bad_event():
    client = app.test_client()
    resp = client.post('/notify', json={"foo": "bar"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'error' in data

def test_notify_valid_event(monkeypatch):
    client = app.test_client()
    # Patch analyze_file to avoid threading/side effects
    called = {}
    def fake_analyze_file(bucket, key):
        called['bucket'] = bucket
        called['key'] = key
    monkeypatch.setattr('app.analyze_file', fake_analyze_file)
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "videos"},
                    "object": {"key": "test.mp4"}
                }
            }
        ]
    }
    resp = client.post('/notify', data=json.dumps(event), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'Analysis started'
    assert data['file'] == 'test.mp4'
    assert called['bucket'] == 'videos'
    assert called['key'] == 'test.mp4' 