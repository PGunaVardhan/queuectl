#!/bin/bash
# Demo script for queuectl
# This walks through the key features step by step

set -e  # Exit on error

echo "╔════════════════════════════════════════════╗"
echo "║     queuectl Demo Walkthrough              ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Clean slate
echo "🧹 Cleaning up any existing database..."
rm -f queuectl.db queuectl.db-shm queuectl.db-wal
echo ""

# Step 1: Configuration
echo "⚙️  Step 1: Configure the queue"
echo "─────────────────────────────────"
queuectl config set max-retries 3
queuectl config set backoff-base 2
queuectl config get
echo ""
read -p "Press Enter to continue..."
echo ""

# Step 2: Enqueue jobs
echo "📝 Step 2: Enqueue some jobs"
echo "─────────────────────────────────"

echo "Adding successful jobs..."
queuectl enqueue '{"id":"job-1","command":"echo Hello from job 1"}'
queuectl enqueue '{"id":"job-2","command":"echo Hello from job 2"}'
queuectl enqueue '{"id":"job-3","command":"sleep 2 && echo Job 3 done"}'

echo ""
echo "Adding a job that will fail..."
queuectl enqueue '{"id":"fail-job","command":"exit 1","max_retries":2}'

echo ""
echo "Adding a delayed job..."
FUTURE_TIME=$(date -u -d '+5 seconds' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -v+5S '+%Y-%m-%dT%H:%M:%SZ')
queuectl enqueue "{\"id\":\"delayed-job\",\"command\":\"echo This job was scheduled\",\"run_at\":\"$FUTURE_TIME\"}"

echo ""
queuectl list
echo ""
read -p "Press Enter to continue..."
echo ""

# Step 3: Check status
echo "📊 Step 3: Check queue status"
echo "─────────────────────────────────"
queuectl status
echo ""
read -p "Press Enter to continue..."
echo ""

# Step 4: Start workers
echo "🔨 Step 4: Starting workers in background..."
echo "─────────────────────────────────"
echo "Starting 2 worker processes (will run for 15 seconds)..."
echo ""

# Start workers in background with timeout
timeout 15s queuectl worker start --count 2 &
WORKER_PID=$!

# Give workers time to process jobs
sleep 3

# Show progress
echo ""
echo "Jobs being processed..."
queuectl status
echo ""

# Wait a bit more
sleep 3

echo "Current status:"
queuectl list
echo ""
read -p "Press Enter to continue..."
echo ""

# Wait for workers to finish or timeout
wait $WORKER_PID 2>/dev/null || true

echo ""
echo "✓ Workers stopped"
echo ""

# Step 5: Check results
echo "📈 Step 5: Check results"
echo "─────────────────────────────────"
echo "Completed jobs:"
queuectl list --state completed
echo ""

echo "Failed jobs (should see our fail-job here after retries):"
queuectl list --state failed
echo ""
read -p "Press Enter to continue..."
echo ""

# Step 6: DLQ
echo "☠️  Step 6: Dead Letter Queue"
echo "─────────────────────────────────"
echo "Jobs that exceeded max retries:"
queuectl dlq list
echo ""

# Check if there are any dead jobs
DEAD_COUNT=$(queuectl list --state dead | grep -c "fail-job" || true)
if [ "$DEAD_COUNT" -gt 0 ]; then
    echo "Let's retry the failed job from DLQ..."
    queuectl dlq retry fail-job
    echo ""
    
    echo "After retry, it's back in pending:"
    queuectl list --state pending
    echo ""
fi

read -p "Press Enter to continue..."
echo ""

# Step 7: Final status
echo "📊 Step 7: Final queue status"
echo "─────────────────────────────────"
queuectl status
echo ""

# Step 8: Cleanup
echo "🧹 Step 8: Cleanup old jobs"
echo "─────────────────────────────────"
echo "In production, you'd run this periodically:"
echo "queuectl cleanup --days 7"
echo ""

echo "╔════════════════════════════════════════════╗"
echo "║     Demo Complete! 🎉                      ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "Key takeaways:"
echo "  ✓ Jobs persist in SQLite database"
echo "  ✓ Multiple workers process concurrently"
echo "  ✓ Failed jobs retry with exponential backoff"
echo "  ✓ Dead Letter Queue catches permanently failed jobs"
echo "  ✓ Scheduled jobs run at the right time"
echo ""
echo "Try it yourself:"
echo "  queuectl worker start --count 3"
echo "  queuectl enqueue '{\"id\":\"test\",\"command\":\"echo test\"}'"
echo "  queuectl status"
echo ""
echo "Database: queuectl.db"
echo "To reset: rm queuectl.db"