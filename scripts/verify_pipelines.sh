#!/bin/bash
# Pipeline Verification Script v1.0
#
# Verifies that all 7 connected pipelines in the voice agent
# actually fired during an E2E test, LLM simulation, or manual session.
#
# Usage:
#   ./scripts/verify_pipelines.sh              # Default: check /tmp/agent_entrypoint.log
#   ./scripts/verify_pipelines.sh /path/to/log # Custom log path
#   ./scripts/verify_pipelines.sh --full       # Full check (includes Redis + PostgreSQL queries)

set -euo pipefail

LOG="${1:-/tmp/agent_entrypoint.log}"
FULL_CHECK=false

if [ "${1:-}" = "--full" ]; then
    FULL_CHECK=true
    LOG="${2:-/tmp/agent_entrypoint.log}"
fi

echo "============================================================"
echo "  Pipeline Verification (7 pipelines)"
echo "============================================================"
echo "  Log file: $LOG"
echo ""

if [ ! -f "$LOG" ]; then
    echo "ERROR: Log file not found: $LOG"
    echo "Make sure the voice agent ran and logged to this file."
    exit 1
fi

# --- 1. Log marker checks ---
echo "--- Log Markers ---"

PASS=0
FAIL=0
CONDITIONAL=0

check_marker() {
    local name="$1"
    local marker="$2"
    local required="$3"  # "required" or "conditional"

    count=$(grep -c "$marker" "$LOG" 2>/dev/null || echo 0)

    if [ "$count" -gt 0 ]; then
        echo "  OK  $name ($count occurrences)"
        PASS=$((PASS + 1))
    elif [ "$required" = "required" ]; then
        echo "  FAIL  $name (0 occurrences) <-- REQUIRED"
        FAIL=$((FAIL + 1))
    else
        echo "  SKIP  $name (0 occurrences) [conditional]"
        CONDITIONAL=$((CONDITIONAL + 1))
    fi
}

# Pipeline 1: Redis registration (entrypoint)
check_marker "Redis registration" "registered in Redis" "required"

# Pipeline 2: PostgreSQL registration (entrypoint)
check_marker "PostgreSQL registration" "registered in PostgreSQL" "required"

# Pipeline 3: KB + CountryDetector (after 6 messages)
check_marker "KB enrichment" "KB context injected" "conditional"

# Pipeline 4: ResearchEngine (needs website URL)
check_marker "Research" "research_launched" "conditional"

# Pipeline 5: Review Phase (needs 16 msgs + 0.5 completion)
check_marker "Review Phase" "review_phase_started" "conditional"

# Pipeline 6: NotificationManager (on finalize)
check_marker "Notifications" "notification_sent" "required"

# Pipeline 7a: record_learning (on finalize + industry + anketa)
check_marker "Learning recorded" "learning_recorded" "conditional"

# Pipeline 7b: PostgreSQL save (on finalize + anketa)
check_marker "PostgreSQL save" "postgres_saved" "conditional"

# Pipeline 7c: Redis cleanup (on finalize)
check_marker "Redis cleanup (finalize)" "session_finalized_in_db" "required"

# Additional useful markers
echo ""
echo "--- Additional Markers ---"
check_marker "Anketa extraction" "periodic_anketa_extracted" "conditional"
check_marker "STT transcription" "USER SPEECH:" "conditional"
check_marker "Agent response" "AGENT STATE:" "conditional"

echo ""
echo "--- Summary ---"
TOTAL=$((PASS + FAIL + CONDITIONAL))
echo "  Passed:      $PASS"
echo "  Failed:      $FAIL"
echo "  Conditional: $CONDITIONAL"
echo "  Total:       $TOTAL"

# --- 2. Redis + PostgreSQL live checks (--full mode) ---
if [ "$FULL_CHECK" = true ]; then
    echo ""
    echo "--- Redis Live Check ---"
    if command -v redis-cli &>/dev/null; then
        REDIS_KEYS=$(redis-cli KEYS "voice:session:*" 2>/dev/null || echo "ERROR")
        if [ "$REDIS_KEYS" = "" ]; then
            echo "  OK  No active session keys (cleaned up after finalize)"
        elif [ "$REDIS_KEYS" = "ERROR" ]; then
            echo "  WARN  Could not connect to Redis"
        else
            echo "  INFO  Active session keys:"
            echo "$REDIS_KEYS" | while read -r key; do
                echo "    $key"
            done
        fi
    else
        echo "  SKIP  redis-cli not available"
    fi

    echo ""
    echo "--- PostgreSQL Live Check ---"
    if command -v psql &>/dev/null; then
        echo "  Interview sessions (recent 3):"
        psql -U interviewer_user -d voice_interviewer -c \
            "SELECT session_id, status, duration_seconds, completeness_score FROM interview_sessions ORDER BY started_at DESC LIMIT 3" \
            2>/dev/null || echo "  WARN  Could not connect to PostgreSQL"

        echo ""
        echo "  Anketas (recent 3):"
        psql -U interviewer_user -d voice_interviewer -c \
            "SELECT anketa_id, company_name, industry FROM anketas ORDER BY created_at DESC LIMIT 3" \
            2>/dev/null || echo "  WARN  Could not connect to PostgreSQL"
    else
        echo "  SKIP  psql not available"
    fi
fi

# --- 3. Final verdict ---
echo ""
echo "============================================================"
if [ "$FAIL" -eq 0 ]; then
    echo "  RESULT: ALL REQUIRED PIPELINES FIRED"
    if [ "$CONDITIONAL" -gt 0 ]; then
        echo "  Note: $CONDITIONAL conditional pipelines did not fire"
        echo "  (normal for short E2E tests; use longer sessions for full coverage)"
    fi
    echo "============================================================"
    exit 0
else
    echo "  RESULT: $FAIL REQUIRED PIPELINES DID NOT FIRE"
    echo "============================================================"
    exit 1
fi
