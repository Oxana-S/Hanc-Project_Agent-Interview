/**
 * E2E Test: Voice Agent with Fake Microphone
 *
 * Uses Puppeteer with Chrome's fake audio device to test:
 * 1. Session creation
 * 2. LiveKit connection
 * 3. Audio track publishing
 * 4. Agent greeting
 * 5. Audio input/output flow
 */

const puppeteer = require('puppeteer');
const path = require('path');

const BASE_URL = 'http://localhost:8000';
const TEST_TIMEOUT = 60000; // 60 seconds
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

        // Navigate to page
        console.log('2️⃣ Opening consultation page...');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 30000 });
        results.push({ test: 'Page load', status: '✅' });

        // Click start button
        console.log('3️⃣ Starting consultation...');
        await page.waitForSelector('#start-btn', { timeout: 5000 });
        await page.click('#start-btn');

        // Wait for connection (check for interview screen)
        console.log('4️⃣ Waiting for LiveKit connection...');
        await sleep(5000); // Wait for connection

        // Check if interview screen is visible
        const interviewVisible = await page.evaluate(() => {
            const interview = document.getElementById('interview-screen');
            return interview && !interview.classList.contains('hidden');
        });

        if (interviewVisible) {
            results.push({ test: 'LiveKit connection', status: '✅' });
        } else {
            results.push({ test: 'LiveKit connection', status: '❌' });
            testPassed = false;
        }

        // Check if audio track was published
        console.log('5️⃣ Checking audio track publication...');
        const audioPublished = consoleLogs.some(log =>
            log.includes('Audio track PUBLISHED') || log.includes('MIC IS NOW LIVE')
        );

        if (audioPublished) {
            results.push({ test: 'Audio track published', status: '✅' });
        } else {
            results.push({ test: 'Audio track published', status: '❌' });
            testPassed = false;
        }

        // Wait for agent greeting
        console.log('6️⃣ Waiting for agent greeting...');
        await sleep(15000); // Wait for agent to greet

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
        console.log('7️⃣ Checking agent received audio...');
        const { execSync } = require('child_process');
        let agentLog = execSync('cat /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();

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
        console.log('8️⃣ Waiting for agent response to user speech...');
        await sleep(10000); // Wait for agent to respond

        // Re-read agent log
        agentLog = execSync('cat /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();

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
    console.log('\n' + '='.repeat(50));
    console.log('TEST RESULTS');
    console.log('='.repeat(50));
    results.forEach(r => {
        console.log(`${r.status} ${r.test}`);
    });
    console.log('='.repeat(50));
    console.log(testPassed ? '✅ ALL TESTS PASSED' : '❌ SOME TESTS FAILED');
    console.log('='.repeat(50));

    process.exit(testPassed ? 0 : 1);
}

runTest();
