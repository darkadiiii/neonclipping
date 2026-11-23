"""Social Scheduler & Dispatch Queue for NeonClipping:
Persistent SQLite-backed scheduler that monitors due posts and publishes
clips automatically at designated times.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
import social_publish

class SocialScheduler:
    def __init__(self, data_dir: Path, autostart: bool = True):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / 'scheduler.db'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.stopped = threading.Event()
        self.wake = threading.Event()
        self._init_db()
        if autostart:
            self.worker = threading.Thread(target=self._run_loop, daemon=True)
            self.worker.start()

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self):
        with self._connect() as db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    id TEXT PRIMARY KEY,
                    clip_id TEXT,
                    platform TEXT,
                    account_id TEXT,
                    metadata TEXT,
                    scheduled_time REAL,
                    status TEXT,
                    result TEXT,
                    created_at REAL,
                    attempts INTEGER DEFAULT 0
                )
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS autopilot_rules (
                    id TEXT PRIMARY KEY,
                    platform TEXT,
                    account_id TEXT,
                    active INTEGER,
                    daily_slots TEXT,
                    max_clips_per_day INTEGER
                )
            ''')

    def get_posts(self) -> list:
        with self._connect() as db:
            rows = db.execute('SELECT * FROM scheduled_posts ORDER BY scheduled_time ASC').fetchall()
            out = []
            for r in rows:
                item = dict(r)
                item['metadata'] = json.loads(item['metadata'] or '{}')
                item['result'] = json.loads(item['result'] or '{}')
                out.append(item)
            return out

    def schedule_post(self, clip_id: str, platform: str, account_id: str, metadata: dict, scheduled_time: float) -> dict:
        post_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._connect() as db:
            db.execute('''
                INSERT INTO scheduled_posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (post_id, clip_id, platform, account_id, json.dumps(metadata), scheduled_time, 'pending', '{}', now, 0))
        self.wake.set()
        return {
            'id': post_id,
            'clip_id': clip_id,
            'platform': platform,
            'scheduled_time': scheduled_time,
            'status': 'pending'
        }

    def cancel_post(self, post_id: str):
        with self._connect() as db:
            db.execute("DELETE FROM scheduled_posts WHERE id = ? AND status = 'pending'", (post_id,))
        return {'ok': True}

    def trigger_now(self, post_id: str):
        with self._connect() as db:
            row = db.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Scheduled post not found')
            db.execute("UPDATE scheduled_posts SET scheduled_time = ? WHERE id = ?", (time.time() - 1, post_id))
        self.wake.set()
        return {'ok': True, 'message': 'Post queued for immediate dispatch'}

    def _process_due_posts(self):
        now = time.time()
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM scheduled_posts WHERE status = 'pending' AND scheduled_time <= ? ORDER BY scheduled_time ASC LIMIT 3",
                (now,)
            ).fetchall()

        for row in rows:
            post_id = row['id']
            clip_id = row['clip_id']
            platform = row['platform']
            account_id = row['account_id']
            metadata = json.loads(row['metadata'] or '{}')

            with self._connect() as db:
                db.execute("UPDATE scheduled_posts SET status = 'publishing', attempts = attempts + 1 WHERE id = ?", (post_id,))

            try:
                res = social_publish.publish_clip(self.data_dir, clip_id, platform, account_id, metadata)
                with self._connect() as db:
                    db.execute(
                        "UPDATE scheduled_posts SET status = 'published', result = ? WHERE id = ?",
                        (json.dumps(res), post_id)
                    )
            except Exception as e:
                err_dict = {'error': str(e), 'failed_at': time.time()}
                with self._connect() as db:
                    db.execute(
                        "UPDATE scheduled_posts SET status = 'failed', result = ? WHERE id = ?",
                        (json.dumps(err_dict), post_id)
                    )

    def _run_loop(self):
        while not self.stopped.is_set():
            try:
                self._process_due_posts()
            except Exception:
                pass
            self.wake.wait(15)
            self.wake.clear()

    def close(self):
        self.stopped.set()
        self.wake.set()
        if hasattr(self, 'worker'):
            self.worker.join(timeout=2)

def attach(app, data_dir: Path):
    scheduler = SocialScheduler(data_dir)

    @app.get('/api/social/schedule')
    def list_scheduled():
        return {'posts': scheduler.get_posts()}

    @app.post('/api/social/schedule')
    def add_schedule(body: dict):
        clip_id = body.get('clip_id')
        platform = body.get('platform')
        account_id = body.get('account_id')
        metadata = body.get('metadata', {})
        scheduled_time = float(body.get('scheduled_time', time.time()))
        if not (clip_id and platform and account_id):
            raise HTTPException(400, 'clip_id, platform, and account_id required')
        return scheduler.schedule_post(clip_id, platform, account_id, metadata, scheduled_time)

    @app.delete('/api/social/schedule/{post_id}')
    def remove_schedule(post_id: str):
        return scheduler.cancel_post(post_id)

    @app.post('/api/social/schedule/{post_id}/publish-now')
    def publish_now_schedule(post_id: str):
        return scheduler.trigger_now(post_id)
