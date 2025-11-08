"""
Worker processes that execute jobs.

Uses multiprocessing to run multiple workers concurrently.
Each worker polls for jobs and executes them using subprocess.
"""

import logging
import multiprocessing
import signal
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from queuectl.storage import JobStore

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(processName)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class Worker:
    """
    A single worker process that consumes jobs from the queue.
    
    Designed to be graceful - finishes current job before stopping.
    """
    
    def __init__(self, worker_id: str, db_path: str = "queuectl.db"):
        self.worker_id = worker_id
        self.store = JobStore(db_path)
        self.running = True
        self.current_job_id: Optional[str] = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Worker {self.worker_id} received shutdown signal")
        self.running = False
    
    def run(self):
        """Main worker loop."""
        logger.info(f"Worker {self.worker_id} started")
        
        while self.running:
            try:
                # Release stale locks from crashed workers
                self.store.release_stale_locks()
                
                # Try to acquire a job
                job = self.store.acquire_job(self.worker_id)
                
                if job:
                    self.current_job_id = job["id"]
                    logger.info(f"Processing job {job['id']}: {job['command']}")
                    
                    success, output, error = self._execute_job(job)
                    
                    if success:
                        self.store.complete_job(job["id"], output)
                        logger.info(f"Job {job['id']} completed")
                    else:
                        self.store.fail_job(job["id"], error)
                        logger.warning(f"Job {job['id']} failed: {error}")
                    
                    self.current_job_id = None
                else:
                    # No jobs available, sleep briefly
                    time.sleep(1)
            
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                time.sleep(5)  # Back off on errors
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    def _execute_job(self, job: dict) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Execute a job command using subprocess.
        
        Returns (success, output, error)
        """
        try:
            timeout = job.get("timeout")
            
            # Run the command
            result = subprocess.run(
                job["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            output = result.stdout
            error = result.stderr
            
            # Success if exit code is 0
            success = result.returncode == 0
            
            if not success:
                error_msg = f"Exit code {result.returncode}"
                if error:
                    error_msg += f": {error}"
                return False, output, error_msg
            
            return True, output, None
        
        except subprocess.TimeoutExpired:
            return False, None, f"Job timed out after {timeout} seconds"
        
        except Exception as e:
            return False, None, f"Execution error: {str(e)}"


class WorkerManager:
    """
    Manages multiple worker processes.
    
    Handles starting, stopping, and tracking workers.
    """
    
    def __init__(self, store: JobStore):
        self.store = store
        self.workers: list[multiprocessing.Process] = []
        self.shutdown_event = multiprocessing.Event()
    
    def start_workers(self, count: int):
        """Start N worker processes."""
        for i in range(count):
            worker_id = f"worker-{uuid.uuid4().hex[:8]}"
            process = multiprocessing.Process(
                target=self._worker_process,
                args=(worker_id, self.store.db_path),
                name=f"Worker-{i+1}",
            )
            process.start()
            self.workers.append(process)
        
        logger.info(f"Started {count} workers")
    
    @staticmethod
    def _worker_process(worker_id: str, db_path: Path):
        """Worker process entry point."""
        worker = Worker(worker_id, str(db_path))
        worker.run()
    
    def stop_workers(self):
        """Stop all workers gracefully."""
        logger.info("Stopping workers...")
        
        for process in self.workers:
            if process.is_alive():
                process.terminate()
        
        # Wait for workers to finish current jobs (max 30 seconds)
        deadline = time.time() + 30
        for process in self.workers:
            remaining = deadline - time.time()
            if remaining > 0:
                process.join(timeout=remaining)
            
            if process.is_alive():
                logger.warning(f"Force killing {process.name}")
                process.kill()
        
        self.workers.clear()
        logger.info("All workers stopped")
    
    def wait(self):
        """Wait for all workers to complete."""
        try:
            for process in self.workers:
                process.join()
        except KeyboardInterrupt:
            pass
    
    def count_active_workers(self) -> int:
        """Count currently running workers."""
        # Check system-wide processes (simple implementation)
        return sum(1 for p in self.workers if p.is_alive())


def start_single_worker(worker_id: Optional[str] = None, db_path: str = "queuectl.db"):
    """
    Helper function to start a single worker (useful for testing).
    """
    worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    worker = Worker(worker_id, db_path)
    worker.run()