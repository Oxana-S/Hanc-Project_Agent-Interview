/**
 * Detailed E2E Voice Test - Full audio pipeline verification
 */

const puppeteer = require('puppeteer');
const path = require('path');
const { execSync } = require('child_process');

const BASE_URL = 'http://localhost:8000';
const TEST_AUDIO_FILE = path.join(__dirname, 'fixtures', 'test_speech_ru.wav');

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function runTest() {
    console.log('🚀 Starting DETAILED E2E Voice Test\n');
    console.log('This test verifies the COMPLETE voice pipeline:\n');
    console.log('1. Client connects to LiveKit room');
    console.log('2. Client publishes audio track (fake mic)');
    console.log('3. Agent subscribes to client audio');
    console.log('4. Agent greets user');
    console.log('5. User speaks (fake audio file)');
    console.log('6. Agent receives and transcribes speech');
    console.log('7. Agent responds with voice');
    console.log('8. Client receives agent audio track');
    console.log('9. Client plays agent audio\n');
    console.log('='.repeat(60) + '\n');

    let browser;
    const results = {};

    try {
        browser = await puppeteer.launch({
            headless: 'new',
            args: [
                '--use-fake-device-for-media-stream',
                '--use-fake-ui-for-media-stream',
                `--use-file-for-fake-audio-capture=${TEST_AUDIO_FILE}`,
                '--autoplay-policy=no-user-gesture-required',
                '--no-sandbox',
            ],
            protocolTimeout: 120000,
        });

        const page = await browser.newPage();

        // Track all console logs
        const allLogs = [];
        page.on('console', msg => {
            const text = msg.text();
            allLogs.push(text);
            // Show key events
            if (text.includes('TrackSubscribed')) {
                console.log('  🔊 CLIENT:', text.match(/TrackSubscribed.*$/)?.[0] || text);
            }
            if (text.includes('Audio element PLAYING')) {
                console.log('  ▶️  CLIENT: Audio element playing');
            }
            if (text.includes('Audio play() blocked')) {
                console.log('  ⛔ CLIENT: Audio BLOCKED by browser');
            }
            if (text.includes('MIC IS NOW LIVE')) {
                console.log('  🎤 CLIENT: Microphone publishing');
            }
            if (text.includes('AUDIO LEVEL')) {
                // Skip frequent audio level logs
            }
        });

        // Navigate and start
        console.log('STEP 1: Loading page...');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 30000 });
        results['page_load'] = true;
        console.log('  ✅ Page loaded\n');

        console.log('STEP 2: Starting consultation...');
        await page.click('#start-btn');
        await sleep(3000);
        results['consultation_started'] = true;
        console.log('  ✅ Consultation started\n');

        console.log('STEP 3: Waiting for LiveKit connection...');
        await sleep(5000);
        const connected = allLogs.some(l => l.includes('room.connect() succeeded'));
        results['livekit_connected'] = connected;
        console.log(`  ${connected ? '✅' : '❌'} LiveKit ${connected ? 'connected' : 'NOT connected'}\n`);

        console.log('STEP 4: Checking client mic published...');
        const micPublished = allLogs.some(l => l.includes('MIC IS NOW LIVE'));
        results['mic_published'] = micPublished;
        console.log(`  ${micPublished ? '✅' : '❌'} Microphone ${micPublished ? 'published' : 'NOT published'}\n`);

        console.log('STEP 5: Waiting for agent track subscription (greeting)...');
        await sleep(10000); // Wait for agent to greet
        const agentTrackSubscribed = allLogs.some(l =>
            l.includes('TrackSubscribed') && l.includes('agent')
        );
        results['agent_track_subscribed'] = agentTrackSubscribed;
        console.log(`  ${agentTrackSubscribed ? '✅' : '❌'} Agent audio track ${agentTrackSubscribed ? 'subscribed' : 'NOT subscribed'}\n`);

        // Check agent log for greeting
        let agentLog = execSync('cat /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();
        const agentGreeted = agentLog.includes('AGENT STATE') && agentLog.includes('speaking');
        results['agent_greeted'] = agentGreeted;
        console.log(`  ${agentGreeted ? '✅' : '❌'} Agent ${agentGreeted ? 'greeted' : 'did NOT greet'}\n`);

        console.log('STEP 6: Waiting for user speech transcription...');
        await sleep(20000); // Wait for VAD + STT
        agentLog = execSync('cat /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();

        const userSpeechMatch = agentLog.match(/USER SPEECH: '([^']+)' \(final=True\)/);
        if (userSpeechMatch) {
            results['user_speech_transcribed'] = true;
            console.log(`  ✅ User speech transcribed: "${userSpeechMatch[1]}"\n`);
        } else {
            results['user_speech_transcribed'] = false;
            console.log('  ❌ User speech NOT transcribed\n');
        }

        console.log('STEP 7: Checking agent response...');
        await sleep(15000); // Wait for agent response
        agentLog = execSync('cat /tmp/agent_entrypoint.log 2>/dev/null || echo ""').toString();

        const agentResponses = agentLog.match(/CONVERSATION: role=assistant, content='\[([^\]]+)\]'/g);
        if (agentResponses && agentResponses.length > 1) {
            results['agent_responded'] = true;
            console.log(`  ✅ Agent responded (${agentResponses.length} messages total)\n`);
        } else if (agentResponses && agentResponses.length === 1) {
            results['agent_responded'] = 'greeting_only';
            console.log('  ⚠️  Agent only greeted, no response to user speech\n');
        } else {
            results['agent_responded'] = false;
            console.log('  ❌ Agent did NOT respond\n');
        }

        console.log('STEP 8: Checking browser audio playback...');
        const audioElements = await page.evaluate(() => {
            return Array.from(document.querySelectorAll('audio')).map(a => ({
                id: a.id,
                muted: a.muted,
                volume: a.volume,
                paused: a.paused,
                played: a.played?.length || 0,
                currentTime: a.currentTime,
                src: a.src || 'blob/mediastream'
            }));
        });

        if (audioElements.length > 0) {
            results['audio_elements'] = audioElements.length;
            console.log(`  ✅ ${audioElements.length} audio element(s) in DOM:`);
            audioElements.forEach((a, i) => {
                console.log(`     [${i}] id=${a.id || 'none'}, muted=${a.muted}, volume=${a.volume}, paused=${a.paused}, played=${a.played}s`);
            });
        } else {
            results['audio_elements'] = 0;
            console.log('  ❌ No audio elements in DOM - agent audio not attached!\n');
        }

        const audioPlayed = allLogs.some(l => l.includes('Audio element PLAYING'));
        const audioBlocked = allLogs.some(l => l.includes('Audio play() blocked'));
        results['audio_played'] = audioPlayed && !audioBlocked;

        if (audioBlocked) {
            console.log('\n  ⛔ AUDIO WAS BLOCKED BY BROWSER AUTOPLAY POLICY!');
        } else if (audioPlayed) {
            console.log('\n  ✅ Audio playback started successfully');
        }

        console.log('\n' + '='.repeat(60));
        console.log('SUMMARY');
        console.log('='.repeat(60));

        const issues = [];
        if (!results['livekit_connected']) issues.push('LiveKit connection failed');
        if (!results['mic_published']) issues.push('Microphone not published');
        if (!results['agent_track_subscribed']) issues.push('Agent audio track not subscribed');
        if (!results['agent_greeted']) issues.push('Agent did not greet');
        if (!results['user_speech_transcribed']) issues.push('User speech not transcribed');
        if (results['agent_responded'] !== true) issues.push('Agent did not respond to user');
        if (results['audio_elements'] === 0) issues.push('No audio elements - agent audio not attached');
        if (audioBlocked) issues.push('Browser blocked audio playback');

        if (issues.length === 0) {
            console.log('\n✅ ALL PIPELINE STAGES WORKING!');
            console.log('\nThe voice agent is functioning correctly:');
            console.log('  - User microphone → LiveKit → Agent: ✅');
            console.log('  - Agent speech → LiveKit → Browser audio: ✅');
        } else {
            console.log('\n❌ ISSUES DETECTED:');
            issues.forEach((issue, i) => console.log(`  ${i + 1}. ${issue}`));
        }

        console.log('\n' + '='.repeat(60) + '\n');

    } catch (error) {
        console.error('Test error:', error.message);
    } finally {
        if (browser) {
            await browser.close();
        }
    }
}

runTest();
