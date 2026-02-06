/**
 * E2E Test: Voice Agent with Fake Microphone (HEADFUL MODE)
 *
 * Visual debugging to see exactly what's happening
 */

const puppeteer = require('puppeteer');
const path = require('path');

const BASE_URL = 'http://localhost:8000';
const TEST_AUDIO_FILE = path.join(__dirname, 'fixtures', 'test_speech_ru.wav');

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function runTest() {
    console.log('🚀 Starting HEADFUL E2E Voice Test\n');

    let browser;

    try {
        // Launch Chrome WITHOUT headless - visible browser
        console.log('1️⃣ Launching VISIBLE browser with fake audio device...');
        browser = await puppeteer.launch({
            headless: false,  // VISIBLE!
            args: [
                '--use-fake-device-for-media-stream',
                '--use-fake-ui-for-media-stream',
                `--use-file-for-fake-audio-capture=${TEST_AUDIO_FILE}`,
                '--disable-web-security',
                '--allow-running-insecure-content',
                '--autoplay-policy=no-user-gesture-required',
                '--no-sandbox',
                '--start-maximized',
            ],
            defaultViewport: null, // Use full window
            protocolTimeout: 120000,
        });

        const page = await browser.newPage();

        // Collect console logs
        page.on('console', msg => {
            const text = msg.text();
            if (text.includes('[HANC]') || text.includes('ERROR') || text.includes('error')) {
                console.log('  📋', text.replace(/%c\[HANC\][^;]+;[^;]+;[^m]+m?\s*/g, '[HANC] '));
            }
        });

        page.on('pageerror', error => {
            console.log('  🔴 Page error:', error.message);
        });

        // Navigate to page
        console.log('2️⃣ Opening consultation page...');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 30000 });

        // Click start button
        console.log('3️⃣ Starting consultation - click start button...');
        await page.waitForSelector('#start-btn', { timeout: 5000 });
        await page.click('#start-btn');

        console.log('4️⃣ Waiting for voice interaction...');
        console.log('   - Agent should greet');
        console.log('   - Fake mic plays Russian speech');
        console.log('   - Agent should respond');

        // Wait and observe
        console.log('\n⏳ Watching for 60 seconds - observe the browser...\n');

        // Periodically check agent logs
        for (let i = 0; i < 12; i++) {
            await sleep(5000);

            const { execSync } = require('child_process');
            const agentLog = execSync('cat /tmp/agent_entrypoint.log 2>/dev/null | tail -5').toString();

            // Parse key events
            if (agentLog.includes('AGENT STATE:')) {
                const stateMatch = agentLog.match(/AGENT STATE: (\w+) -> (\w+)/);
                if (stateMatch) {
                    console.log(`  🤖 Agent: ${stateMatch[1]} → ${stateMatch[2]}`);
                }
            }
            if (agentLog.includes('USER SPEECH:') && agentLog.includes('final=True')) {
                const speechMatch = agentLog.match(/USER SPEECH: '([^']+)'/);
                if (speechMatch) {
                    console.log(`  👤 User said: "${speechMatch[1]}"`);
                }
            }
            if (agentLog.includes('CONVERSATION: role=assistant')) {
                const respMatch = agentLog.match(/CONVERSATION: role=assistant, content='\[['"]([^'"]+)['"]\]'/);
                if (respMatch) {
                    console.log(`  🤖 Agent said: "${respMatch[1].substring(0, 60)}..."`);
                }
            }
        }

        // Check final state
        console.log('\n📊 Final state check...');

        const messageCount = await page.evaluate(() => {
            return document.querySelectorAll('.message').length;
        });
        console.log(`  💬 Messages in UI: ${messageCount}`);

        const audioElements = await page.evaluate(() => {
            return Array.from(document.querySelectorAll('audio')).map(a => ({
                id: a.id,
                muted: a.muted,
                volume: a.volume,
                paused: a.paused,
                currentTime: a.currentTime,
            }));
        });
        console.log(`  🔊 Audio elements:`, audioElements);

        console.log('\n✅ Test complete. Browser stays open for manual inspection.');
        console.log('   Press Ctrl+C to close.\n');

        // Keep browser open for manual inspection
        await sleep(300000); // 5 minutes

    } catch (error) {
        console.error('Test error:', error.message);
    } finally {
        if (browser) {
            await browser.close();
        }
    }
}

runTest();
