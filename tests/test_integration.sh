#!/bin/bash
# Integration tests for queuectl
# Tests real workflows end-to-end

set -e

echo "Running queuectl integration tests..."
echo "======================================"

# Cleanup
rm -f test_integration.db

# Use test database
export TEST_DB="test_integration.db"

# Test 1: Basic job enqueue and process
echo ""
echo "Test 1: Basic job processing"
echo "----------------------------"

# Enqueue a job
OUTPUT=$(queuectl enqueue '{"id":"int-test-1","command":"echo SUCCESS"}' 2>&1)
if [[ $OUTPUT != *"✓"* ]]; then
    echo "FAIL: Job enqueue failed"
    exit 1
fi
echo "✓ Job enqueued"

# Start worker for 5 seconds
timeout 5s queuectl worker start --count 1 &
WORKER_PID=$!
sleep 2

# Check if job completed
COMPLETED=$(queuectl list --state completed | grep -c "int-test-1" || true)
if [ "$COMPLETED" -eq 0 ]; then
    echo "FAIL: Job not completed"
    kill $WORKER_PID 2>/dev/null || true
    exit 1
fi
echo "✓ Job completed successfully"

wait $WORKER_PID 2>/dev/null || true

# Test 2: Failed job with retry
echo ""
echo "Test 2: Job retry on failure"
echo "-----------------------------"

queuectl config set max-retries 2
queuectl config set backoff-base 1  # Fast backoff for testing

queuectl enqueue '{"id":"int-test-fail","command":"exit 1"}'
echo "✓ Failed job enqueued"

# Run worker
timeout 8s queuectl worker start --count 1 &
WORKER_PID=$!
sleep 7  # Wait for retries

# Check if job is in DLQ
DEAD=$(queuectl list --state dead | grep -c "int-test-fail" || true)
if [ "$DEAD" -eq 0 ]; then
    echo "FAIL: Job not in DLQ after max retries"
    kill $WORKER_PID 2>/dev/null || true
    exit 1
fi
echo "✓ Job moved to DLQ after retries"

wait $WORKER_PID 2>/dev/null || true

# Test 3: Concurrent workers
echo ""
echo "Test 3: Concurrent worker processing"
echo "-------------------------------------"

# Enqueue 10 jobs
for i in {1..10}; do
    queuectl enqueue "{\"id\":\"concurrent-$i\",\"command\":\"sleep 0.5 && echo Job $i\"}"
done
echo "✓ 10 jobs enqueued"

# Start 3 workers
timeout 10s queuectl worker start --count 3 &
WORKER_PID=$!
sleep 6

# Check completion
COMPLETED=$(queuectl list --state completed | grep -c "concurrent-" || true)
if [ "$COMPLETED" -lt 8 ]; then
    echo "FAIL: Not enough jobs completed (expected >=8, got $COMPLETED)"
    kill $WORKER_PID 2>/dev/null || true
    exit 1
fi
echo "✓ Multiple workers processed jobs concurrently ($COMPLETED/10 completed)"

wait $WORKER_PID 2>/dev/null || true

# Test 4: DLQ retry
echo ""
echo "Test 4: DLQ retry functionality"
echo "--------------------------------"

queuectl dlq retry int-test-fail
PENDING=$(queuectl list --state pending | grep -c "int-test-fail" || true)
if [ "$PENDING" -eq 0 ]; then
    echo "FAIL: Job not moved back to pending"
    exit 1
fi
echo "✓ Job successfully retried from DLQ"

# Test 5: Status and stats
echo ""
echo "Test 5: Status command"
echo "----------------------"

queuectl status > /dev/null
echo "✓ Status command works"

# Cleanup
rm -f test_integration.db test_integration.db-shm test_integration.db-wal

echo ""
echo "======================================"
echo "All integration tests passed! ✅"
echo "======================================"