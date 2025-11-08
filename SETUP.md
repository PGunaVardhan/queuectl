# Setup & Installation Guide

Complete step-by-step instructions to get `queuectl` running on your machine.

## Prerequisites

- **Python 3.10 or higher** (check with `python3 --version`)
- **pip** package manager
- **Git** (for cloning the repository)

## Installation

### Option 1: Install from source (recommended for development)

```bash
# 1. Clone the repository
git clone https://github.com/PGunaVardhan/queuectl.git
cd queuectl

# 2. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Verify installation
queuectl --help
```

### Option 2: Install with pip (for users)

```bash
pip install queuectl
```

### Option 3: Using Poetry

```bash
# 1. Install Poetry if you don't have it
curl -sSL https://install.python-poetry.org | python3 -

# 2. Clone and install
git clone https://github.com/PGunaVardhan/queuectl.git
cd queuectl
poetry install

# 3. Activate the environment
poetry shell

# 4. Verify installation
queuectl --help
```

## Quick Test

```bash
# Enqueue a test job
queuectl enqueue '{"id":"test-1","command":"echo Hello World"}'

# Start a worker in one terminal
queuectl worker start --count 1

# In another terminal, check status
queuectl status
queuectl list --state completed
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=queuectl --cov-report=html

# Run a specific test
pytest tests/test_queuectl.py::TestJobStore::test_add_job -v
```

## Running the Demo

```bash
# Make the demo script executable
chmod +x demo.sh

# Run the interactive demo
./demo.sh
```

## Database Location

By default, `queuectl` creates `queuectl.db` in your current directory. To use a different location:

```bash
# Set environment variable (if we supported it)
export QUEUECTL_DB="/path/to/custom/queuectl.db"

# Or modify the default in cli.py
```

## Troubleshooting

### Issue: `queuectl: command not found`

**Solution**: Ensure the virtual environment is activated and the package is installed:
```bash
source venv/bin/activate
pip install -e .
```

### Issue: `ModuleNotFoundError: No module named 'typer'`

**Solution**: Install dependencies:
```bash
pip install typer[all] rich
```

### Issue: Workers not processing jobs

**Solutions**:
1. Check if workers are running: `queuectl status`
2. Check database permissions: `ls -l queuectl.db`
3. Look for stale locks: Workers auto-release after 5 minutes
4. Check logs: Workers print to stdout

### Issue: Database is locked

**Solution**: This happens if:
- Multiple processes are trying to write simultaneously (normal, will retry)
- Database file is on NFS (not supported - use local filesystem)
- Stale lock files (delete `queuectl.db-shm` and `queuectl.db-wal`)

### Issue: Jobs stuck in "processing" state

**Solution**: 
```bash
# Stale locks are auto-released after 5 minutes
# To manually reset:
sqlite3 queuectl.db "UPDATE jobs SET state='pending', locked_by=NULL WHERE state='processing'"
```

## Development Setup

For contributing or modifying the code:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run code formatter
black queuectl/ tests/

# Run linter
ruff check queuectl/ tests/

# Run type checker (optional)
mypy queuectl/
```

## Production Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/queuectl-worker.service`:

```ini
[Unit]
Description=queuectl worker
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/queuectl
ExecStart=/path/to/venv/bin/queuectl worker start --count 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable queuectl-worker
sudo systemctl start queuectl-worker
sudo systemctl status queuectl-worker
```

### Docker (Optional)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY queuectl/ queuectl/

RUN pip install -e .

CMD ["queuectl", "worker", "start", "--count", "4"]
```

Build and run:
```bash
docker build -t queuectl .
docker run -v $(pwd)/queuectl.db:/app/queuectl.db queuectl
```

### Monitoring

Set up a cron job to monitor the DLQ:

```bash
# Add to crontab: crontab -e
*/10 * * * * /path/to/venv/bin/queuectl dlq list | mail -s "queuectl DLQ Alert" admin@example.com
```

## Upgrading

```bash
# Pull latest changes
git pull origin main

# Reinstall
pip install -e .

# Restart workers
# (systemd will handle this automatically if configured)
```

## Uninstallation

```bash
# Remove the package
pip uninstall queuectl

# Delete the database
rm queuectl.db queuectl.db-shm queuectl.db-wal

# Remove the source code
cd .. && rm -rf queuectl/
```

## Next Steps

1. Read the [README.md](README.md) for usage examples
2. Check [architecture.md](architecture.md) for design details
3. Run the demo: `./demo.sh`
4. Start building your own jobs!

## Getting Help

- **Issues**: https://github.com/PGunaVardhan/queuectl/issues
- **Discussions**: https://github.com/PGunaVardhan/queuectl/discussions
- **Email**: pulagamguna4142@gmail.com