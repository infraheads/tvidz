import pytest
import json
from app import app, analysis_results
from db import add_video, add_timestamps, find_duplicates

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

def test_clear_db():
    client = app.test_client()
    resp = client.post('/admin/clear-db')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'cleared'

def test_build_info():
    client = app.test_client()
    resp = client.get('/build-info')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'inspector' in data
    assert 'build_date' in data['inspector']

def test_duplicate_detection():
    # Clean DB first
    client = app.test_client()
    client.post('/admin/clear-db')
    # Add two videos with different timestamps
    v1 = add_video('a.mp4')
    v2 = add_video('b.mp4')
    add_timestamps(v1.id, [1.0, 2.0, 3.0, 4.0, 5.0])
    add_timestamps(v2.id, [10.0, 20.0, 30.0, 40.0, 50.0])
    # Should not be duplicates
    dups = find_duplicates([10.0, 20.0, 30.0, 40.0, 50.0], min_match=5)
    assert (v1.id, 0) not in dups
    assert (v2.id, 5) in dups
    # Add a third video with same timestamps as v1
    v3 = add_video('c.mp4')
    add_timestamps(v3.id, [1.0, 2.0, 3.0, 4.0, 5.0])
    dups = find_duplicates([1.0, 2.0, 3.0, 4.0, 5.0], min_match=5)
    assert (v1.id, 5) in dups
    assert (v3.id, 5) in dups 