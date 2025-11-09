"""
Tests for queuectl - because untested code is just a ticking time bomb.

Run with: pytest tests/
"""

import os
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from queuectl.storage import JobStore
from queuectl.models import JobState
from queuectl.worker import Worker


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    yield str(db_path)
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def store(temp_db):
    """Create a JobStore instance."""
    return JobStore(temp_db)


class TestJobStore:
    """Test the persistence layer."""
    
    def test_add_job(self, store):
        """Test adding a job to the queue."""
        job_id = store.add_job(command="echo 'hello'", job_id="test-1")
        
        assert job_id == "test-1"
        
        jobs = store.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["command"] == "echo 'hello'"
        assert jobs[0]["state"] == JobState.PENDING.value
    
    def test_acquire_job(self, store):
        """Test job acquisition with locking."""
        store.add_job(command="sleep 1", job_id="job-1")
        
        # Acquire job
        job = store.acquire_job("worker-1")
        assert job is not None
        assert job["id"] == "job-1"
        assert job["state"] == JobState.PROCESSING.value
        
        # Try to acquire again - should return None (already locked)
        job2 = store.acquire_job("worker-2")
        assert job2 is None
    
    def test_complete_job(self, store):
        """Test marking job as completed."""
        job_id = store.add_job(command="echo 'done'")
        job = store.acquire_job("worker-1")
        
        store.complete_job(job["id"], output="done\n")
        
        jobs = store.list_jobs(state=JobState.COMPLETED.value)
        assert len(jobs) == 1
        assert jobs[0]["output"] == "done\n"
    
    def test_fail_job_with_retry(self, store):
        """Test job failure triggers retry."""
        store.set_config("backoff_base", 2)
        job_id = store.add_job(command="false", max_retries=3)
        
        job = store.acquire_job("worker-1")
        store.fail_job(job["id"], error="Command failed")
        
        jobs = store.list_jobs(state=JobState.PENDING.value)
        assert len(jobs) == 1
        assert jobs[0]["attempts"] == 1
        assert jobs[0]["run_at"] is not None  # Scheduled for retry
    
    def test_fail_job_moves_to_dlq(self, store):
        """Test job moves to DLQ after max retries."""
        job_id = store.add_job(command="false", max_retries=2)
        
        # Fail 3 times (attempts 1, 2, 3)
        for i in range(3):
            job = store.acquire_job("worker-1")
            if job:
                store.fail_job(job["id"], error=f"Attempt {i+1} failed")
                time.sleep(0.1)  # Small delay for retry scheduling
        
        jobs = store.list_jobs(state=JobState.DEAD.value)
        assert len(jobs) == 1
        assert jobs[0]["attempts"] == 3
    
    def test_retry_dlq_job(self, store):
        """Test retrying a job from DLQ."""
        job_id = store.add_job(command="false", max_retries=1)
        
        # Move to DLQ
        job = store.acquire_job("worker-1")
        store.fail_job(job["id"], error="Failed")
        job = store.acquire_job("worker-1")
        store.fail_job(job["id"], error="Failed again")
        
        # Retry from DLQ
        store.retry_job(job_id)
        
        jobs = store.list_jobs(state=JobState.PENDING.value)
        assert len(jobs) == 1
        assert jobs[0]["attempts"] == 0  # Reset
    
    def test_config(self, store):
        """Test configuration management."""
        store.set_config("max_retries", 5)
        assert store.get_config("max_retries") == 5
        
        store.set_config("backoff_base", 3)
        assert store.get_config("backoff_base") == 3
    
    def test_cleanup_old_jobs(self, store):
        """Test cleaning up old completed jobs."""
        # Add some completed jobs
        for i in range(5):
            job_id = store.add_job(command=f"echo {i}")
            job = store.acquire_job("worker-1")
            store.complete_job(job["id"])
        
        # Manually update timestamps to be old
        with store._get_conn() as conn:
            old_time = (datetime.utcnow() - timedelta(days=10)).isoformat()
            conn.execute("UPDATE jobs SET updated_at = ?", (old_time,))
        
        deleted = store.cleanup_old_jobs(days=7)
        assert deleted == 5


class TestWorker:
    """Test worker functionality."""
    
    def test_execute_successful_command(self, temp_db):
        """Test worker executes a successful command."""
        store = JobStore(temp_db)
        job_id = store.add_job(command="echo 'test'")
        
        worker = Worker("test-worker", temp_db)
        job = store.acquire_job(worker.worker_id)
        
        success, output, error = worker._execute_job(job)
        
        assert success is True
        assert "test" in output
        assert error is None
    
    def test_execute_failing_command(self, temp_db):
        """Test worker handles failing commands."""
        store = JobStore(temp_db)
        job_id = store.add_job(command="exit 1")
        
        worker = Worker("test-worker", temp_db)
        job = store.acquire_job(worker.worker_id)
        
        success, output, error = worker._execute_job(job)
        
        assert success is False
        assert error is not None
        assert "Exit code 1" in error
    
    def test_execute_with_timeout(self, temp_db):
        """Test job timeout handling."""
        store = JobStore(temp_db)
        job_id = store.add_job(command="sleep 10", timeout=1)
        
        worker = Worker("test-worker", temp_db)
        job = store.acquire_job(worker.worker_id)
        
        success, output, error = worker._execute_job(job)
        
        assert success is False
        assert "timed out" in error.lower()
    
    def test_invalid_command(self, temp_db):
        """Test worker handles invalid commands gracefully."""
        store = JobStore(temp_db)
        job_id = store.add_job(command="thisisnotarealcommand12345")
        
        worker = Worker("test-worker", temp_db)
        job = store.acquire_job(worker.worker_id)
        
        success, output, error = worker._execute_job(job)
        
        assert success is False
        assert error is not None


class TestConcurrency:
    """Test concurrent worker scenarios."""
    
    def test_multiple_workers_no_overlap(self, store):
        """Test that multiple workers don't process the same job."""
        # Add multiple jobs
        job_ids = [store.add_job(command=f"echo {i}") for i in range(10)]
        
        # Acquire jobs with different workers
        acquired = []
        for i in range(10):
            job = store.acquire_job(f"worker-{i}")
            if job:
                acquired.append(job["id"])
        
        # All jobs should be acquired by different workers
        assert len(set(acquired)) == len(acquired)  # No duplicates
        assert len(acquired) == 10
    
    def test_release_stale_locks(self, store):
        """Test that stale locks are released."""
        job_id = store.add_job(command="sleep 1")
        
        # Acquire and lock the job
        job = store.acquire_job("worker-1")
        assert job is not None
        
        # Manually set lock time to be stale
        with store._get_conn() as conn:
            old_time = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
            conn.execute("UPDATE jobs SET locked_at = ? WHERE id = ?", (old_time, job_id))
        
        # Release stale locks
        released = store.release_stale_locks(minutes=5)
        assert released == 1
        
        # Job should be acquirable again
        job2 = store.acquire_job("worker-2")
        assert job2 is not None
        assert job2["id"] == job_id


class TestExponentialBackoff:
    """Test retry backoff behavior."""
    
    def test_backoff_calculation(self, store):
        """Test that retry delays follow exponential backoff."""
        store.set_config("backoff_base", 2)
        job_id = store.add_job(command="false", max_retries=5)
        
        retry_times = []
        
        for i in range(3):
            job = store.acquire_job("worker-1")
            if job:
                before_fail = datetime.utcnow()
                store.fail_job(job["id"], error=f"Attempt {i+1}")
                
                # Check retry time
                jobs = store.list_jobs(state=JobState.PENDING.value)
                if jobs:
                    run_at = datetime.fromisoformat(jobs[0]["run_at"])
                    delay = (run_at - before_fail).total_seconds()
                    retry_times.append(delay)
        
        # Verify exponential growth: 2^1=2, 2^2=4, 2^3=8
        assert len(retry_times) == 3
        assert 1.5 < retry_times[0] < 2.5  # ~2 seconds
        assert 3.5 < retry_times[1] < 4.5  # ~4 seconds
        assert 7.5 < retry_times[2] < 8.5  # ~8 seconds


class TestScheduledJobs:
    """Test delayed/scheduled job execution."""
    
    def test_scheduled_job_not_acquired_early(self, store):
        """Test that scheduled jobs aren't acquired before run_at."""
        future_time = datetime.utcnow() + timedelta(hours=1)
        job_id = store.add_job(command="echo 'future'", run_at=future_time)
        
        # Try to acquire - should return None
        job = store.acquire_job("worker-1")
        assert job is None
    
    def test_scheduled_job_acquired_when_ready(self, store):
        """Test that scheduled jobs are acquired when ready."""
        past_time = datetime.utcnow() - timedelta(seconds=1)
        job_id = store.add_job(command="echo 'past'", run_at=past_time)
        
        # Should be acquirable
        job = store.acquire_job("worker-1")
        assert job is not None
        assert job["id"] == job_id