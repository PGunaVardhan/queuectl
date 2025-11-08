# Examples

This directory contains example scripts and job definitions to help you get started with `queuectl`.

## Files

### `example_jobs.json`

Sample job definitions demonstrating different features:
- Database backup job with high retry count
- Email sending with timeout
- Image processing batch job
- Log cleanup with minimal retries
- Scheduled report generation

**Usage:**
```bash
# View the examples
cat examples/example_jobs.json

# Enqueue all examples programmatically
python examples/enqueue_jobs.py
```

### `enqueue_jobs.py`

Python script demonstrating how to programmatically enqueue jobs using the `JobStore` class directly instead of the CLI.

**Usage:**
```bash
python examples/enqueue_jobs.py
```

This shows:
- Simple job enqueueing
- Configuring max retries
- Setting job timeouts
- Scheduling delayed jobs
- Bulk enqueueing from JSON

## Common Patterns

### Pattern 1: Simple Task

```bash
queuectl enqueue '{"id":"task-1","command":"python process.py --input data.csv"}'
```

### Pattern 2: Task with Retry Configuration

```bash
queuectl enqueue '{
  "id":"resilient-task",
  "command":"curl https://api.example.com/data",
  "max_retries": 5
}'
```

### Pattern 3: Task with Timeout

```bash
queuectl enqueue '{
  "id":"quick-task",
  "command":"python slow_script.py",
  "timeout": 60
}'
```

### Pattern 4: Scheduled Task

```bash
# Run at specific time (ISO 8601 format)
queuectl enqueue '{
  "id":"scheduled-task",
  "command":"python backup.py",
  "run_at":"2025-11-10T02:00:00Z"
}'
```

### Pattern 5: Batch Processing

```bash
# Enqueue multiple related jobs
for i in {1..10}; do
  queuectl enqueue "{
    \"id\":\"batch-$i\",
    \"command\":\"python process_chunk.py --chunk $i\"
  }"
done
```

## Real-World Use Cases

### 1. Email Queue

```python
from queuectl.storage import JobStore

store = JobStore()

# Enqueue emails
for user in users:
    store.add_job(
        command=f"python send_email.py --to {user.email} --template welcome",
        job_id=f"email-{user.id}",
        max_retries=3,
        timeout=30
    )
```

### 2. Image Processing Pipeline

```python
# Stage 1: Resize images
for image in images:
    store.add_job(
        command=f"python resize.py --input {image} --output resized/{image}",
        job_id=f"resize-{image}"
    )

# Stage 2: Generate thumbnails (could check for resize completion first)
for image in images:
    store.add_job(
        command=f"python thumbnail.py --input resized/{image}",
        job_id=f"thumb-{image}"
    )
```

### 3. Scheduled Reports

```python
from datetime import datetime, timedelta

# Daily report at 6 AM
tomorrow_6am = datetime.utcnow().replace(hour=6, minute=0) + timedelta(days=1)

store.add_job(
    command="python generate_daily_report.py",
    job_id="daily-report-" + tomorrow_6am.strftime("%Y%m%d"),
    run_at=tomorrow_6am
)
```

### 4. Data Pipeline

```bash
#!/bin/bash
# data_pipeline.sh

# Extract
queuectl enqueue '{"id":"extract","command":"python extract_data.py"}'

# Transform (depends on extract - manual coordination for now)
queuectl enqueue '{"id":"transform","command":"python transform_data.py"}'

# Load
queuectl enqueue '{"id":"load","command":"python load_data.py"}'
```

## Tips

1. **Use meaningful job IDs**: Makes debugging easier
2. **Set appropriate timeouts**: Prevent runaway jobs
3. **Configure retries based on job type**: Network calls need more retries than local operations
4. **Monitor the DLQ**: Failed jobs need investigation
5. **Clean up completed jobs**: Run `queuectl cleanup` periodically

## Creating Your Own Examples

```python
#!/usr/bin/env python3
"""
my_job_enqueuer.py - Custom job enqueuing script
"""

from queuectl.storage import JobStore

def enqueue_my_jobs():
    store = JobStore()
    
    # Your jobs here
    store.add_job(
        command="your-command",
        job_id="your-id",
        max_retries=3
    )
    
    print("✅ Jobs enqueued!")

if __name__ == "__main__":
    enqueue_my_jobs()
```

## Next Steps

1. Modify `example_jobs.json` with your own tasks
2. Run `python examples/enqueue_jobs.py` to test
3. Start workers: `queuectl worker start --count 3`
4. Monitor: `queuectl status`