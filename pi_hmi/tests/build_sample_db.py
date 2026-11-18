"""Build a disposable Phase 0 review database; never overwrites an existing file."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys


def build(path):
    path = Path(path)
    # Exclusive creation prevents accidental replacement, including concurrent use.
    with path.open('xb'):
        pass
    fixtures = Path(__file__).parent / 'fixtures'
    with closing(sqlite3.connect(path)) as db:
        db.executescript((fixtures/'schema_v1.sql').read_text(encoding='utf-8'))
        db.executescript((fixtures/'seed.sql').read_text(encoding='utf-8'))
        image = json.loads((fixtures/'camera_metadata.json').read_text())
        db.execute('INSERT INTO images VALUES(1,1,1,?,?,?,?,?,?,?)',
                   [image[k] for k in ['file_path','timestamp_utc','sha256','size_bytes','width_px','height_px','capture_reason']])
        db.execute("INSERT INTO ml_inferences VALUES(1,1,'2026-10-01T00:00:01+00:00','uncertain / out-of-scope',0.5,'fixture-only',1,10)")
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python tests/build_sample_db.py NEW_PATH.sqlite3')
    build(sys.argv[1])
    print('Created synthetic Phase 0 database: ' + sys.argv[1])
