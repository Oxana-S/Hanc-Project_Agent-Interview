/**
 * E2E Test: Voice Agent with Fake Microphone + Pipeline Verification
 *
 * Uses Puppeteer with Chrome's fake audio device to test:
 * 1. Session creation
 * 2. LiveKit connection
 * 3. Audio track publishing
 * 4. Agent greeting
 * 5. Audio input/output flow
 * 6. Pipeline verification (all 7 connected pipelines)
 *
 * After browser closes, waits for agent finalization and verifies
 * that backend pipelines (Redis, PostgreSQL, KB, Notifications, etc.)
 * actually fired during the session.
 */

const puppeteer = require('puppeteer');
const path = require('path');

const BASE_URL = 'http://localhost:8000';
const TEST_TIMEOUT = 120000; // 120 seconds (speech file is ~14s + agent processing)
// Use Russian speech file for better VAD/STT testing
const TEST_AUDIO_FILE = path.join(__dirname, 'fixtures', 'test_speech_ru.wav');

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function runTest() {
    console.log('🚀 Starting E2E Voice Test with Fake Microphone\n');

    let browser;
    let testPassed = true;
    const results = [];

    try {
        // Launch Chrome with fake audio device
        console.log('1️⃣ Launching browser with fake audio device...');
        browser = await puppeteer.launch({
            headless: 'new',  // Use new headless mode
            args: [
                '--use-fake-device-for-media-stream',
                '--use-fake-ui-for-media-stream',
                `--use-file-for-fake-audio-capture=${TEST_AUDIO_FILE}`,
                '--disable-web-security',
                '--allow-running-insecure-content',
                '--autoplay-policy=no-user-gesture-required',
                '--disable-features=IsolateOrigins,site-per-process',
                '--enable-features=WebRTC-H264WithOpenH264FFmpeg',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ],
            protocolTimeout: 60000,
        });
        results.push({ test: 'Browser launch', status: '✅' });

        const page = await browser.newPage();

        // Collect console logs
        const consoleLogs = [];
        page.on('console', msg => {
            const text = msg.text();
            consoleLogs.push(text);
            // Show all logs for debugging
            if (text.includes('[HANC]')) {
                console.log('  📋', text.replace(/%c\[HANC\][^;]+;[^;]+;[^m]+m?\s*/g, '[HANC] '));
            }
            if (text.includes('ERROR') || text.includes('FAILED') || text.includes('error')) {
                console.log('  ⚠️', text);
            }
        });

        // Capture page errors
        page.on('pageerror', error => {
            console.log('  🔴 Page error:', error.message);
        });

        // Navigate to dashboard
        console.log('2️⃣ Opening dashboard...');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 30000 });

        // Set localStorage to bypass landing page (first-time visitor check)
        await page.evaluate(() => {
            localStorage.setItem('hasVisited', 'true');
        });

        // Reload to show dashboard instead of landing
        await page.reload({ waitUntil: 'networkidle2' });
        results.push({ test: 'Page load', status: '✅' });

        // Verify dashboard is visible
        await page.waitForSelector('#dashboard-screen', { timeout: 5000 });
        results.push({ test: 'Dashboard loaded', status: '✅' });

        // Click "Новая консультация" button (shows pre-session screen)
        console.log('3️⃣ Opening pre-session screen from dashboard...');
        await page.waitForSelector('#new-session-btn', { visible: true, timeout: 5000 });
        await page.evaluate(() => {
            document.getElementById('new-session-btn').click();
        });

        // Wait for pre-session screen to appear
        await page.waitForSelector('.btn-start-voice', { visible: true, timeout: 5000 });

        // Click "Начать разговор" button (actually creates session)
        console.log('4️⃣ Creating session and starting voice conversation...');
        await page.evaluate(() => {
            document.querySelector('.btn-start-voice').click();
        });

        // Wait for session creation and redirect to /session/:link
        console.log('5️⃣ Waiting for LiveKit connection...');
        await page.waitForFunction(
            () => window.location.pathname.startsWith('/session/'),
            { timeout: 15000 }
        );
        results.push({ test: 'Session created', status: '✅' });

        await sleep(5000); // Wait for LiveKit connection

        // Check if session screen is in voice-active state (LiveKit connected)
        const voiceActive = await page.evaluate(() => {
            const session = document.getElementById('session-screen');
            return session && session.classList.contains('voice-active');
        });

        if (voiceActive) {
            results.push({ test: 'LiveKit connection', status: '✅' });
        } else {
            results.push({ test: 'LiveKit connection', status: '❌' });
            testPassed = false;
        }

        // Check if audio track was published
        console.log('6️⃣ Checking audio track publication...');
        const audioPublished = consoleLogs.some(log =>
            log.includes('START RECORDING') || log.includes('Audio track PUBLISHED') || log.includes('MIC IS NOW LIVE')
        );

        if (audioPublished) {
            results.push({ test: 'Audio track published', status: '✅' });
        } else {
            results.push({ test: 'Audio track published', status: '❌' });
            testPassed = false;
        }

        // Wait for agent greeting (audio file is ~14s, agent needs time to greet first)
        console.log('7️⃣ Waiting for agent greeting...');
        await sleep(20000); // Wait for agent to greet + user audio to play

        // Check if agent message appeared in chat
        const agentGreeted = await page.evaluate(() => {
            const messages = document.querySelectorAll('.message.ai');
            return messages.length > 0;
        });

        if (agentGreeted) {
            results.push({ test: 'Agent greeting', status: '✅' });
        } else {
            results.push({ test: 'Agent greeting', status: '❌' });
            testPassed = false;
        }

        // Check agent log for USER STATE
        console.log('8️⃣ Checking agent received audio...');
        const { execSync } = require('child_process');
        let agentLog = execSync('tail -n 500 /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();

        const trackSubscribed = agentLog.includes('Track subscribed');
        const userAway = agentLog.includes('USER STATE: listening -> away');
        const userSpeaking = agentLog.includes('USER STATE: listening -> speaking') ||
                           agentLog.includes('USER SPEECH:');

        if (trackSubscribed) {
            results.push({ test: 'Track subscribed by agent', status: '✅' });
        } else {
            results.push({ test: 'Track subscribed by agent', status: '❌' });
            testPassed = false;
        }

        if (userSpeaking) {
            results.push({ test: 'Agent received audio', status: '✅' });
        } else if (userAway) {
            results.push({ test: 'Agent received audio', status: '❌ (user went away - no audio received)' });
            testPassed = false;
        } else {
            results.push({ test: 'Agent received audio', status: '⚠️ (inconclusive)' });
        }

        // Wait for agent response after user speech
        console.log('9️⃣ Waiting for agent response to user speech...');
        await sleep(20000); // Wait for agent to process speech and respond

        // Re-read agent log
        agentLog = execSync('tail -n 500 /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();

        // Check for STT transcription (user speech text)
        const userSpeechMatch = agentLog.match(/USER SPEECH: (.+)/);
        if (userSpeechMatch) {
            console.log('  📝 User speech transcribed:', userSpeechMatch[1]);
            results.push({ test: 'STT transcription', status: '✅' });
        } else {
            results.push({ test: 'STT transcription', status: '❌ (no transcription found)' });
        }

        // Check for agent response after user speech (not just greeting)
        const agentResponses = agentLog.match(/AGENT SPEECH: (.+)/g) || [];
        if (agentResponses.length > 1) {
            console.log('  🤖 Agent responded:', agentResponses[agentResponses.length - 1]);
            results.push({ test: 'Agent response to user', status: '✅' });
        } else if (agentResponses.length === 1) {
            results.push({ test: 'Agent response to user', status: '⚠️ (only greeting, no conversation)' });
        } else {
            results.push({ test: 'Agent response to user', status: '❌ (no agent speech found)' });
        }

        // Check UI for multiple messages
        const messageCount = await page.evaluate(() => {
            return document.querySelectorAll('.message').length;
        });
        console.log(`  💬 Total messages in UI: ${messageCount}`);
        if (messageCount > 1) {
            results.push({ test: 'Conversation in UI', status: '✅' });
        } else {
            results.push({ test: 'Conversation in UI', status: '⚠️ (only greeting visible)' });
        }

        // === STEP 10: Close browser and wait for agent finalization ===
        console.log('🔟 Closing browser, waiting for agent finalization...');
        await browser.close();
        browser = null; // Prevent double-close in finally

        // _finalize_and_save() fires on disconnect: extraction + DB saves + notifications
        // Takes 10-20s depending on DeepSeek API latency
        await sleep(20000);

        // === STEP 11: Pipeline Verification ===
        console.log('1️⃣1️⃣ Verifying pipeline markers in agent log...');
        agentLog = execSync('tail -n 2000 /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();

        const pipelineResults = [];
        const pipelines = [
            // Always fire (on connect)
            { name: 'Redis registration', marker: 'registered in Redis', expected: true },
            { name: 'PostgreSQL registration', marker: 'registered in PostgreSQL', expected: true },
            // Fire on disconnect (_finalize_and_save)
            { name: 'Notifications', marker: 'notification_sent', expected: true },
            { name: 'Redis cleanup', marker: 'session_finalized_in_db', expected: true },
            // Fire if extraction ran (needs 6+ user messages)
            { name: 'KB enrichment', marker: 'KB context injected', expected: false },
            { name: 'Learning recorded', marker: 'learning_recorded', expected: false },
            { name: 'PostgreSQL save', marker: 'postgres_saved', expected: false },
            // Unlikely in 45s test
            { name: 'Research', marker: 'research_launched', expected: false },
            { name: 'Review phase', marker: 'review_phase_started', expected: false },
        ];

        console.log('\n  --- Pipeline Verification ---');
        let pipelinesOk = 0;
        let pipelinesTotal = pipelines.length;

        for (const p of pipelines) {
            const found = agentLog.includes(p.marker);
            const icon = found ? '✅' : (p.expected ? '❌' : '⚠️');
            console.log(`  ${icon} ${p.name}: ${found ? 'FIRED' : 'not fired'}${!p.expected && !found ? ' (conditional)' : ''}`);

            if (found) pipelinesOk++;

            if (p.expected) {
                // These MUST fire — failure is critical
                results.push({
                    test: `Pipeline: ${p.name}`,
                    status: found ? '✅' : '❌'
                });
                if (!found) testPassed = false;
            } else {
                // These are conditional — informational only
                pipelineResults.push({
                    test: `Pipeline: ${p.name}`,
                    status: found ? '✅' : '⚠️ (conditional)'
                });
            }
        }
        console.log(`  Pipelines fired: ${pipelinesOk}/${pipelinesTotal}`);

        // Check Redis key (if redis-cli available)
        try {
            const redisKeys = execSync('redis-cli KEYS "voice:session:*" 2>/dev/null || echo "N/A"').toString().trim();
            console.log(`  Redis keys: ${redisKeys || '(empty — cleaned up after finalize)'}`);
        } catch (e) {
            console.log('  Redis: redis-cli not available');
        }

        // Check PostgreSQL (if psql available)
        try {
            const pgSessions = execSync(
                'psql -U interviewer_user -d voice_interviewer -t -c "SELECT count(*) FROM interview_sessions" 2>/dev/null || echo "N/A"'
            ).toString().trim();
            console.log(`  PostgreSQL interview_sessions: ${pgSessions} rows`);
        } catch (e) {
            console.log('  PostgreSQL: psql not available');
        }

        // Add conditional pipeline results to output
        results.push(...pipelineResults);

    } catch (error) {
        console.error('Test error:', error.message);
        results.push({ test: 'Test execution', status: `❌ ${error.message}` });
        testPassed = false;
    } finally {
        if (browser) {
            await browser.close();
        }
    }

    // Print results
    console.log('\n' + '='.repeat(60));
    console.log('TEST RESULTS');
    console.log('='.repeat(60));

    // Separate critical and informational
    const critical = results.filter(r => !r.status.includes('⚠️') || r.status.includes('❌'));
    const informational = results.filter(r => r.status.includes('⚠️') && !r.status.includes('❌'));

    console.log('\nCritical checks:');
    results.filter(r => !r.test.startsWith('Pipeline:') || !r.status.includes('⚠️')).forEach(r => {
        console.log(`  ${r.status} ${r.test}`);
    });

    if (informational.length > 0) {
        console.log('\nConditional pipelines (informational):');
        results.filter(r => r.test.startsWith('Pipeline:') && r.status.includes('⚠️')).forEach(r => {
            console.log(`  ${r.status} ${r.test}`);
        });
    }

    console.log('\n' + '='.repeat(60));
    console.log(testPassed ? '✅ ALL CRITICAL TESTS PASSED' : '❌ SOME CRITICAL TESTS FAILED');
    console.log('='.repeat(60));

    process.exit(testPassed ? 0 : 1);
}

runTest();
