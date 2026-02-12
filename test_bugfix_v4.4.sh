#!/bin/bash

# Test script for v4.4 bugfix - Microphone reconnect fixes
# Tests critical bugs #1-6 and UX improvements #1-3

set -e

echo "=========================================="
echo "BUGFIX v4.4 - Test Suite"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check if critical files were modified
echo "Test 1: Verify files were modified"
echo "-----------------------------------"

if git diff HEAD~1 src/voice/consultant.py | grep -q "extra="; then
    echo -e "${GREEN}✓${NC} БАГ #1 (Logger fix) - FOUND in consultant.py"
else
    echo -e "${RED}✗${NC} БАГ #1 (Logger fix) - NOT FOUND"
fi

if git diff HEAD~1 src/voice/consultant.py | grep -q "fresh_session = _session_mgr.get_session"; then
    echo -e "${GREEN}✓${NC} БАГ #2 (Race condition) - FOUND in consultant.py"
else
    echo -e "${RED}✗${NC} БАГ #2 (Race condition) - NOT FOUND"
fi

if git diff HEAD~1 public/app.js | grep -q "status === 'processing'"; then
    echo -e "${GREEN}✓${NC} БАГ #3 (Frontend reconnect) - FOUND in app.js"
else
    echo -e "${RED}✗${NC} БАГ #3 (Frontend reconnect) - NOT FOUND"
fi

if git diff HEAD~1 public/app.js | grep -q "RoomEvent.Connected"; then
    echo -e "${GREEN}✓${NC} БАГ #4 (Event-driven) - FOUND in app.js"
else
    echo -e "${RED}✗${NC} БАГ #4 (Event-driven) - NOT FOUND"
fi

if git diff HEAD~1 public/app.js | grep -q "localParticipant is null"; then
    echo -e "${GREEN}✓${NC} БАГ #5 (Guard check) - FOUND in app.js"
else
    echo -e "${RED}✗${NC} БАГ #5 (Guard check) - NOT FOUND"
fi

if git diff HEAD~1 public/app.js | grep -q "sessionData.status === 'paused'"; then
    echo -e "${GREEN}✓${NC} БАГ #6 (UI restore) - FOUND in app.js"
else
    echo -e "${RED}✗${NC} БАГ #6 (UI restore) - NOT FOUND"
fi

echo ""

# Test 2: Check Python syntax
echo "Test 2: Python syntax validation"
echo "----------------------------------"

if ./venv/bin/python -m py_compile src/voice/consultant.py 2>/dev/null; then
    echo -e "${GREEN}✓${NC} consultant.py - Syntax OK"
else
    echo -e "${RED}✗${NC} consultant.py - Syntax ERROR"
    exit 1
fi

echo ""

# Test 3: Check JavaScript syntax (basic)
echo "Test 3: JavaScript syntax validation"
echo "-------------------------------------"

if node -c public/app.js 2>/dev/null; then
    echo -e "${GREEN}✓${NC} app.js - Syntax OK"
else
    echo -e "${RED}✗${NC} app.js - Syntax ERROR (check manually)"
fi

echo ""

# Test 4: Grep for old patterns (should NOT exist)
echo "Test 4: Check for removed patterns"
echo "-----------------------------------"

if grep -q 'event_log.info("dialogue_saved_sync", session_id=' src/voice/consultant.py 2>/dev/null; then
    echo -e "${RED}✗${NC} OLD logger pattern still exists!"
else
    echo -e "${GREEN}✓${NC} OLD logger pattern removed"
fi

if grep -q 'setTimeout(() => this.startRecording(), 1000);' public/app.js 2>/dev/null; then
    echo -e "${RED}✗${NC} OLD setTimeout pattern still exists!"
else
    echo -e "${GREEN}✓${NC} OLD setTimeout pattern removed"
fi

echo ""

# Test 5: Check database (if sessions.db exists)
echo "Test 5: Database check (session 39139356)"
echo "------------------------------------------"

if [ -f "data/sessions.db" ]; then
    STATUS=$(sqlite3 data/sessions.db "SELECT status FROM sessions WHERE session_id='39139356';" 2>/dev/null || echo "N/A")
    if [ "$STATUS" = "paused" ]; then
        echo -e "${GREEN}✓${NC} Session 39139356 status: $STATUS (CORRECT)"
    elif [ "$STATUS" = "N/A" ]; then
        echo -e "${YELLOW}⚠${NC} Session 39139356 not found (create test session first)"
    else
        echo -e "${RED}✗${NC} Session 39139356 status: $STATUS (EXPECTED: paused)"
    fi

    HISTORY_LEN=$(sqlite3 data/sessions.db "SELECT LENGTH(dialogue_history) FROM sessions WHERE session_id='39139356';" 2>/dev/null || echo "0")
    if [ "$HISTORY_LEN" -gt "1000" ]; then
        echo -e "${GREEN}✓${NC} Dialogue history length: $HISTORY_LEN bytes (SAVED)"
    elif [ "$HISTORY_LEN" = "0" ]; then
        echo -e "${YELLOW}⚠${NC} Dialogue history empty (test session first)"
    else
        echo -e "${RED}✗${NC} Dialogue history too short: $HISTORY_LEN bytes"
    fi
else
    echo -e "${YELLOW}⚠${NC} Database not found (data/sessions.db). Start server first."
fi

echo ""

# Test 6: Server status
echo "Test 6: Server status check"
echo "----------------------------"

if lsof -ti:8000 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Server is running on port 8000"

    # Try to fetch session status
    if command -v curl &> /dev/null; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/session/39139356/status 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "200" ]; then
            echo -e "${GREEN}✓${NC} API endpoint /api/session/.../status is accessible"
        elif [ "$HTTP_CODE" = "404" ]; then
            echo -e "${YELLOW}⚠${NC} Session 39139356 not found (404)"
        else
            echo -e "${RED}✗${NC} API returned HTTP $HTTP_CODE"
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC} Server is NOT running. Start with: make start"
fi

echo ""
echo "=========================================="
echo "MANUAL TESTING REQUIRED"
echo "=========================================="
echo ""
echo "Please test manually using Scenario A:"
echo ""
echo "1. Create new consultation"
echo "2. Talk for 2-3 minutes (10+ messages)"
echo "3. Click 'Сохранить и выйти'"
echo "4. Verify: status in DB = 'paused'"
echo "5. Return via link /session/<unique_link>"
echo "6. EXPECTED:"
echo "   - Pause overlay visible"
echo "   - Mic button disabled"
echo "   - Play button '▶' visible"
echo "   - Connection status: 'Подключено'"
echo "7. Click '▶' (Resume)"
echo "8. EXPECTED:"
echo "   - Mic activates"
echo "   - Can continue dialogue"
echo ""
echo "=========================================="
echo "Test suite completed!"
echo "=========================================="
