#!/usr/bin/env python3
"""
Example script to programmatically enqueue jobs.

Usage:
    python examples/enqueue_jobs.py
"""

import json
from queuectl.storage import JobStore


def main():
    store = JobStore()
    
    # Example 1: Simple job
    job_id = store.add_job(
        command="echo 'Hello from Python'",
        job_id="python-job-1"
    )
    print(f"✓ Enqueued job: {job_id}")
    
    # Example 2: Job with retry config
    job_id = store.add_job(
        command="python -c 'import sys; sys.exit(1)'",  # Will fail
        job_id="failing-job",
        max_retries=5
    )
    print(f"✓ Enqueued failing job: {job_id}")
    
    # Example 3: Job with timeout
    job_id = store.add_job(
        command="sleep 100",
        job_id="timeout-job",
        timeout=5  # Kill after 5 seconds
    )
    print(f"✓ Enqueued timeout job: {job_id}")
    
    # Example 4: Scheduled job
    from datetime import datetime, timedelta
    future_time = datetime.utcnow() + timedelta(minutes=5)
    
    job_id = store.add_job(
        command="echo 'This job was scheduled'",
        job_id="scheduled-job",
        run_at=future_time
    )
    print(f"✓ Enqueued scheduled job: {job_id} (runs at {future_time.isoformat()})")
    
    # Example 5: Bulk enqueue from JSON file
    print("\n📄 Loading jobs from example_jobs.json...")
    try:
        with open("examples/example_jobs.json") as f:
            jobs = json.load(f)
        
        for job_data in jobs:
            job_id = store.add_job(
                command=job_data["command"],
                job_id=job_data["id"],
                max_retries=job_data.get("max_retries", 3),
                timeout=job_data.get("timeout"),
                run_at=datetime.fromisoformat(job_data["run_at"]) if "run_at" in job_data else None
            )
            print(f"  ✓ {job_id}")
    except FileNotFoundError:
        print("  ⚠ example_jobs.json not found, skipping bulk enqueue")
    
    print(f"\n✅ All jobs enqueued! Run 'queuectl status' to see them.")


if __name__ == "__main__":
    main()