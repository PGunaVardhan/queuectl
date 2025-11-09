# queuectl

> A lightweight, persistent job queue that actually works. Built for developers who need background processing without the operational overhead of Redis, Celery, or a dedicated message broker.

## What is this?

`queuectl` is a CLI-based job queue system that stores jobs in SQLite, runs them with worker processes, and handles failures gracefully with exponential backoff. Think of it as a minimal, self-contained alternative to heavier queue systems when you just need to run background tasks reliably.

Perfect for:
- Processing long-running tasks in web applications
- Running scheduled maintenance scripts
- Building reliable data pipelines
- Any scenario where "run this command later" is the requirement

## Features

- **Persistent storage**: Jobs survive restarts (SQLite with WAL mode)
- **Multiple workers**: Run N concurrent worker processes
- **Automatic retries**: Exponential backoff (configurable base and max retries)
- **Dead Letter Queue (DLQ)**: Permanently failed jobs go here for manual inspection
- **Job scheduling**: Delay execution with `run_at` timestamps
- **Graceful shutdown**: Workers finish their current job before exiting
- **Safe concurrency**: Row-level locking prevents duplicate processing
- **Rich CLI**: Pretty tables and colors via Typer + Rich

## Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/PGunaVardhan/queuectl.git
cd queuectl

# Install dependencies
pip install -e .

# Or with poetry
poetry install
```

### Basic Usage

```bash
# Enqueue a simple job
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'

# Start 3 worker processes
queuectl worker start --count 3

# Check queue status
queuectl status

# List pending jobs
queuectl list --state pending

# View the DLQ
queuectl dlq list

# Retry a failed job
queuectl dlq retry job1
```

## Architecture

### Job Lifecycle

```
   ┌─────────┐
   │ pending │ ←──────────────────┐
   └────┬────┘                    │
        │                         │ (retry with backoff)
        │ (worker acquires)       │
        ▼                         │
  ┌────────────┐           ┌─────┴────┐
  │ processing │──────────→│  failed  │
  └─────┬──────┘  (error)  └──────────┘
        │                         │
        │ (success)               │ (max retries exceeded)
        ▼                         ▼
   ┌───────────┐            ┌─────────┐
   │ completed │            │  dead   │ (DLQ)
   └───────────┘            └─────────┘
```

### Concurrency Model

Workers use SQLite row-level locking to safely grab jobs:

1. Worker queries for pending jobs with `SELECT ... LIMIT 1`
2. Worker updates the job to `processing` state with its `worker_id`
3. If the update succeeds (no other worker grabbed it), proceed
4. Otherwise, try again

This approach works because SQLite's WAL mode allows concurrent reads and a single writer. For higher throughput, you'd want PostgreSQL with `SELECT FOR UPDATE SKIP LOCKED`, but SQLite handles ~100-1000 jobs/sec which is plenty for most use cases.

### Retry Strategy

Failed jobs use exponential backoff:

```python
delay = base ** attempts  # seconds
```

Default: `base=2`, so failures at attempts 1, 2, 3 wait 2s, 4s, 8s respectively.

After `max_retries` (default: 3), the job moves to the Dead Letter Queue (`state=dead`).

### Storage

Jobs are stored in `queuectl.db` (SQLite) with this schema:

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT,
    output TEXT,
    run_at TEXT,  -- For scheduled jobs
    timeout INTEGER,  -- Command timeout in seconds
    locked_by TEXT,  -- Worker ID holding lock
    locked_at TEXT   -- Lock timestamp
);
```

WAL mode is enabled for better concurrency. Stale locks (from crashed workers) are automatically released after 5 minutes.

## Configuration

```bash
# Set max retries
queuectl config set max-retries 5

# Set backoff base (delay = base^attempts)
queuectl config set backoff-base 3

# View all config
queuectl config get
```

## Advanced Features

### Job Timeouts

```bash
queuectl enqueue '{"id":"timeout-test","command":"sleep 100","timeout":5}'
```

Jobs exceeding the timeout are killed and marked as failed.

### Scheduled Jobs

```bash
# Run job 1 hour from now
queuectl enqueue '{
  "id":"scheduled-job",
  "command":"python backup.py",
  "run_at":"2025-11-09T15:00:00Z"
}'
```

Workers won't pick up the job until `run_at` is reached.

### Output Logging

Job stdout/stderr is captured and stored in the `output` field:

```bash
# Check output
queuectl list --state completed
```

## Testing

### Run the test suite

```bash
# Install pytest
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_queuectl.py::TestJobStore::test_fail_job_moves_to_dlq -v
```

### Manual testing script

```bash
# See demo.sh for a step-by-step demo
./demo.sh
```

## Demo Walkthrough

1. **Setup**: Initialize the database (happens automatically on first run)
2. **Enqueue jobs**: Add a mix of successful and failing jobs
3. **Start workers**: Launch 2-3 workers to process the queue
4. **Watch it work**: Use `queuectl status` and `queuectl list` to observe
5. **Test failure handling**: See failed jobs move to DLQ after retries
6. **Retry from DLQ**: Manually retry a DLQ job

See `demo.sh` for the full script.

## Production Considerations

### ⚠️ Security Warning

**This tool executes shell commands directly via `subprocess.run(shell=True)`.** Only enqueue jobs from trusted sources. Running arbitrary commands can be dangerous:

```bash
# Safe
queuectl enqueue '{"id":"safe","command":"echo hello"}'

# DANGEROUS - never do this with untrusted input
queuectl enqueue '{"id":"bad","command":"rm -rf /"}'
```

For production:
- Whitelist allowed commands
- Run workers in containers with limited permissions
- Use a proper job serialization format (not raw shell commands)

### Scaling

- **Single machine**: SQLite + multiprocessing handles ~100-1000 jobs/sec
- **Multiple machines**: Migrate to PostgreSQL for distributed workers
- **High throughput**: Consider RabbitMQ, Redis, or managed services (AWS SQS, GCP Pub/Sub)

### Monitoring

Check queue health:

```bash
# Job counts by state
queuectl status

# Old failed jobs
queuectl dlq list

# Database size
ls -lh queuectl.db
```

Consider adding:
- Prometheus metrics export
- Alerting on DLQ size
- Job duration tracking

## Project Structure

```
queuectl/
├── queuectl/
│   ├── __init__.py
│   ├── cli.py          # Typer CLI interface
│   ├── models.py       # Job data models
│   ├── storage.py      # SQLite persistence layer
│   └── worker.py       # Worker processes
├── tests/
│   ├── __init__.py
│   └── test_queuectl.py  # pytest tests
├── demo.sh             # Demo walkthrough script
├── architecture.md     # Design decisions
├── README.md           # You are here
├── LICENSE             # MIT
├── pyproject.toml      # Dependencies
└── .gitignore
```

## Design Decisions

See `architecture.md` for detailed explanations of:
- Why SQLite instead of Redis
- Row-level locking strategy
- Process-based vs thread-based workers
- Trade-offs and limitations

## Contributing

This is a personal project built for a job application, but PRs are welcome! Areas for improvement:

- [ ] PostgreSQL backend option
- [ ] Job priority queue
- [ ] Cron-style recurring jobs
- [ ] Web dashboard (basic version in `web/` directory)
- [ ] Prometheus metrics exporter

## About the Author

I'm a CS grad who believes in pragmatic solutions over perfect ones. This project was built to demonstrate:
- Clean, readable Python code
- Understanding of concurrency and persistence
- Ability to ship a working product with docs and tests

I chose SQLite because it's underrated, multiprocessing because it's simple, and exponential backoff because it's elegant. If you're hiring backend engineers who care about craft, let's talk.

## License

MIT - See LICENSE file

## Citations

This project was built from scratch, but drew inspiration from:

- **Job queue patterns**: "Queueing theory" and worker pool patterns are well-established CS concepts. References: [Wikipedia - Job queue](https://en.wikipedia.org/wiki/Job_queue)
- **SQLite concurrency**: SQLite WAL mode documentation - [sqlite.org](https://www.sqlite.org/wal.html)
- **Exponential backoff**: Standard retry strategy used in distributed systems - [AWS Architecture Blog](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- **CLI design**: Inspired by modern CLI tools (Docker, kubectl, gh) that use subcommands and rich output

Libraries used:
- `typer` for CLI framework (MIT license)
- `rich` for terminal formatting (MIT license)
- `pytest` for testing (MIT license)

All code in this repository is original work written specifically for this project.
The demo video for the project can be found at [This google drive link](https://drive.google.com/file/d/1emVxdNsOBq8ixQAzkGddN1Bt6tZyXMAc/view?usp=sharing).

---

**Built with ☕ and a deadline**
