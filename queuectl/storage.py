"""
Persistence layer using SQLite.

We're using raw SQL because it's explicit and we want full control over locking.
SQLAlchemy would work too, but this keeps dependencies minimal.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from contextlib import contextmanager

from queuectl.models import Job, JobState


class JobStore:
    """
    Thread-safe job storage with SQLite.
    
    Uses row-level locking to prevent concurrent workers from grabbing the same job.
    """
    
    def __init__(self, db_path: str = "queuectl.db"):
        self.db_path = Path(db_path)
        self._init_db()
    
    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            # Jobs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT,
                    output TEXT,
                    run_at TEXT,
                    timeout INTEGER,
                    locked_by TEXT,
                    locked_at TEXT
                )
            """)
            
            # Config table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Set default config if not exists
            conn.execute("""
                INSERT OR IGNORE INTO config (key, value) VALUES ('max_retries', '3')
            """)
            conn.execute("""
                INSERT OR IGNORE INTO config (key, value) VALUES ('backoff_base', '2')
            """)
            
            # Create indices for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_state_created ON jobs(state, created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_run_at ON jobs(run_at)
            """)
    
    def add_job(
        self,
        command: str,
        job_id: Optional[str] = None,
        max_retries: Optional[int] = None,
        run_at: Optional[datetime] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """Add a new job to the queue."""
        job_id = job_id or str(uuid.uuid4())
        max_retries = max_retries if max_retries is not None else self.get_config("max_retries")
        now = datetime.utcnow().isoformat()
        
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO jobs (id, command, state, attempts, max_retries, created_at, updated_at, run_at, timeout)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (job_id, command, JobState.PENDING.value, 0, max_retries, now, now,
                  run_at.isoformat() if run_at else None, timeout))
        
        return job_id
    
    def acquire_job(self, worker_id: str) -> Optional[Dict]:
        """
        Atomically acquire the next pending job for processing.
        
        This is where the magic happens - we use SELECT FOR UPDATE to lock the row,
        preventing other workers from grabbing it.
        """
        with self._get_conn() as conn:
            # Find and lock a pending job that's ready to run
            now = datetime.utcnow().isoformat()
            
            cursor = conn.execute("""
                SELECT * FROM jobs
                WHERE state = ?
                  AND (run_at IS NULL OR run_at <= ?)
                  AND (locked_by IS NULL OR locked_at < ?)
                ORDER BY created_at
                LIMIT 1
            """, (JobState.PENDING.value, now, 
                  (datetime.utcnow() - timedelta(minutes=5)).isoformat()))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            job_dict = dict(row)
            
            # Lock it
            conn.execute("""
                UPDATE jobs
                SET state = ?, locked_by = ?, locked_at = ?, updated_at = ?
                WHERE id = ? AND state = ?
            """, (JobState.PROCESSING.value, worker_id, now, now, 
                  job_dict["id"], JobState.PENDING.value))
            
            # Verify we got the lock
            if conn.total_changes == 0:
                return None
            
            job_dict["state"] = JobState.PROCESSING.value
            return job_dict
    
    def complete_job(self, job_id: str, output: Optional[str] = None):
        """Mark job as completed."""
        now = datetime.utcnow().isoformat()
        
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE jobs
                SET state = ?, updated_at = ?, output = ?, locked_by = NULL, locked_at = NULL
                WHERE id = ?
            """, (JobState.COMPLETED.value, now, output, job_id))
    
    def fail_job(self, job_id: str, error: str):
        """
        Handle job failure with retry logic.
        
        If max retries exceeded, move to DLQ (dead state).
        Otherwise, schedule retry with exponential backoff.
        """
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Job {job_id} not found")
            
            job = dict(row)
            attempts = job["attempts"] + 1
            now = datetime.utcnow()
            
            if attempts > job["max_retries"]:
                # Move to DLQ
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, attempts = ?, error = ?, updated_at = ?, 
                        locked_by = NULL, locked_at = NULL
                    WHERE id = ?
                """, (JobState.DEAD.value, attempts, error, now.isoformat(), job_id))
            else:
                # Schedule retry with exponential backoff
                backoff_base = self.get_config("backoff_base")
                delay_seconds = backoff_base ** attempts
                retry_at = now + timedelta(seconds=delay_seconds)
                
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, attempts = ?, error = ?, updated_at = ?, run_at = ?,
                        locked_by = NULL, locked_at = NULL
                    WHERE id = ?
                """, (JobState.PENDING.value, attempts, error, now.isoformat(), 
                      retry_at.isoformat(), job_id))
    
    def retry_job(self, job_id: str):
        """Move a DLQ job back to pending."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT state FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Job {job_id} not found")
            
            if row["state"] != JobState.DEAD.value:
                raise ValueError(f"Job {job_id} is not in DLQ (state: {row['state']})")
            
            now = datetime.utcnow().isoformat()
            conn.execute("""
                UPDATE jobs
                SET state = ?, attempts = 0, error = NULL, updated_at = ?, run_at = NULL
                WHERE id = ?
            """, (JobState.PENDING.value, now, job_id))
    
    def list_jobs(self, state: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """List jobs, optionally filtered by state."""
        with self._get_conn() as conn:
            if state:
                cursor = conn.execute("""
                    SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC LIMIT ?
                """, (state, limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict[str, int]:
        """Get job counts by state."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT state, COUNT(*) as count FROM jobs GROUP BY state
            """)
            return {row["state"]: row["count"] for row in cursor.fetchall()}
    
    def get_config(self, key: str) -> int:
        """Get configuration value."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return int(row["value"]) if row else 3
    
    def set_config(self, key: str, value: int):
        """Set configuration value."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)
            """, (key, str(value)))
    
    def cleanup_old_jobs(self, days: int = 7) -> int:
        """Delete completed jobs older than N days."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        with self._get_conn() as conn:
            conn.execute("""
                DELETE FROM jobs
                WHERE state = ? AND updated_at < ?
            """, (JobState.COMPLETED.value, cutoff))
            return conn.total_changes
    
    def release_stale_locks(self, minutes: int = 5):
        """Release locks held for longer than N minutes (for crashed workers)."""
        cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        now = datetime.utcnow().isoformat()
        
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE jobs
                SET state = ?, locked_by = NULL, locked_at = NULL, updated_at = ?
                WHERE locked_at < ? AND state = ?
            """, (JobState.PENDING.value, now, cutoff, JobState.PROCESSING.value))
            return conn.total_changes