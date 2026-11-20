"""Library deletion removes records, never export/render media or active jobs."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def library(tmp_path, monkeypatch):
    from core import db, job_store
    from api.routers import exports
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'library.db')
    db.init_db()
    app = FastAPI()
    app.include_router(exports.router)
    return TestClient(app, client=("127.0.0.1", 50000)), db, job_store


def test_delete_export_record_keeps_file_and_other_records(library, tmp_path):
    client, db, _ = library
    media = tmp_path / 'voice.wav'
    media.write_bytes(b'original media')
    with db.db_conn() as conn:
        for id in ('remove', 'keep'):
            conn.execute('INSERT INTO export_history (id, filename, destination_path, mode, created_at) VALUES (?, ?, ?, ?, ?)',
                         (id, 'voice.wav', str(media), 'clone', 1))
    assert client.delete('/export/history/remove').status_code == 200
    assert client.delete('/export/history/remove').status_code == 200
    assert [r['id'] for r in client.get('/export/history').json()] == ['keep']
    assert media.read_bytes() == b'original media'


@pytest.mark.parametrize('path', ['/export/history/remove'])
def test_remote_clients_cannot_delete_local_library(library, path):
    local, _, _ = library
    with TestClient(local.app, client=('203.0.113.5', 50000)) as remote:
        assert remote.delete(path).status_code == 403
