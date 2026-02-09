/**
 * Voice Interviewer Web UI
 * Клиентское приложение для голосового взаимодействия
 */

// Debug logger - all messages prefixed for easy filtering in console
const LOG = {
    info: (...args) => console.log('%c[HANC]', 'color: #2563eb; font-weight: bold', ...args),
    warn: (...args) => console.warn('%c[HANC]', 'color: #d97706; font-weight: bold', ...args),
    error: (...args) => console.error('%c[HANC]', 'color: #dc2626; font-weight: bold', ...args),
    step: (n, total, msg) => console.log(
        `%c[HANC STEP ${n}/${total}]`, 'color: #059669; font-weight: bold', msg
    ),
    event: (name, data) => console.log(
        `%c[HANC EVENT: ${name}]`, 'color: #7c3aed; font-weight: bold', data || ''
    ),
};

class VoiceInterviewerApp {
    constructor() {
        LOG.info('=== VoiceInterviewerApp initializing ===');

        // LiveKit
        this.room = null;
        this.localParticipant = null;
        this.audioTrack = null;
        this.audioLevelInterval = null;

        // State
        this.sessionId = null;
        this.uniqueLink = null;
        this.isRecording = false;
        this.isConnected = false;
        this.agentAudioElements = new Map(); // trackSid -> { track, element }

        // Anketa state
        this.anketaPollingInterval = null;
        this.anketaSaveTimeout = null;
        this.focusedField = null;
        this.localEdits = {};
        this.lastServerAnketa = {};

        // Anketa field definitions (order matters for display)
        this.anketaFields = [
            'company_name', 'contact_name', 'contact_role',
            'phone', 'email', 'industry', 'company_description',
            'services', 'current_problems', 'agent_tasks', 'integrations',
            'call_volume', 'budget', 'timeline', 'additional_notes'
        ];

        // Array fields (stored as arrays on server, shown as newline-separated text)
        this.arrayFields = new Set([
            'services', 'current_problems', 'agent_tasks', 'integrations'
        ]);

        // DOM Elements
        this.elements = {
            startBtn: document.getElementById('start-btn'),
            micBtn: document.getElementById('mic-btn'),
            stopBtn: document.getElementById('stop-btn'),
            newBtn: document.getElementById('new-btn'),
            connectionStatus: document.getElementById('connection-status'),
            phaseIndicator: document.getElementById('phase-indicator'),
            progressFill: document.getElementById('progress-fill'),
            progressText: document.getElementById('progress-text'),
            dialogueContainer: document.getElementById('dialogue-container'),
            voiceIndicator: document.getElementById('voice-indicator'),
            voiceStatus: document.getElementById('voice-status'),
            resultsStats: document.getElementById('results-stats'),
            resultsFiles: document.getElementById('results-files'),
            // Anketa elements
            anketaForm: document.getElementById('anketa-form'),
            anketaStatusBadge: document.getElementById('anketa-status-badge'),
            confirmAnketaBtn: document.getElementById('confirm-anketa-btn'),
            saveLeaveBtn: document.getElementById('save-leave-btn'),
            copyLinkBtn: document.getElementById('copy-link-btn'),
        };

        // Screens
        this.screens = {
            welcome: document.getElementById('welcome-screen'),
            interview: document.getElementById('interview-screen'),
            results: document.getElementById('results-screen'),
        };

        // Check LiveKit SDK
        if (typeof LivekitClient !== 'undefined') {
            LOG.info('LiveKit JS SDK loaded:', LivekitClient.version || 'version unknown');
        } else {
            LOG.error('LiveKit JS SDK NOT LOADED - voice will not work!');
        }

        this.init();
        LOG.info('=== VoiceInterviewerApp ready ===');
    }

    init() {
        this.elements.startBtn.addEventListener('click', () => this.startSession());
        this.elements.micBtn.addEventListener('click', () => this.toggleRecording());
        this.elements.stopBtn.addEventListener('click', () => this.endSession());
        this.elements.newBtn.addEventListener('click', () => this.resetSession());

        this.elements.confirmAnketaBtn.addEventListener('click', () => this.confirmAnketa());
        this.elements.saveLeaveBtn.addEventListener('click', () => this.saveAndLeave());
        this.elements.copyLinkBtn.addEventListener('click', () => this.copySessionLink());

        this.setupAnketaFieldListeners();
        this.checkSessionResumption();
    }

    // ===== Anketa Field Listeners =====

    setupAnketaFieldListeners() {
        const formFields = this.elements.anketaForm.querySelectorAll('input, textarea');
        formFields.forEach(field => {
            const fieldName = field.dataset.field;

            field.addEventListener('focus', () => {
                this.focusedField = fieldName;
            });

            field.addEventListener('blur', () => {
                if (this.focusedField === fieldName) {
                    this.focusedField = null;
                }
            });

            field.addEventListener('input', () => {
                this.localEdits[fieldName] = true;
                this.scheduleAnketaSave();
            });
        });
    }

    // ===== Session Resumption =====

    async checkSessionResumption() {
        const path = window.location.pathname;
        const match = path.match(/^\/session\/([a-f0-9-]+)$/i);
        if (!match) return;

        const link = match[1];
        LOG.info('Attempting session resumption for link:', link);

        try {
            let sessionData = null;

            let response = await fetch(`/api/session/by-link/${link}`);
            if (response.ok) {
                sessionData = await response.json();
                LOG.info('Session found by link:', sessionData.session_id);
            } else {
                response = await fetch(`/api/session/${link}`);
                if (response.ok) {
                    sessionData = await response.json();
                    LOG.info('Session found by ID:', sessionData.session_id);
                }
            }

            if (sessionData) {
                this.sessionId = sessionData.session_id || link;
                this.uniqueLink = sessionData.unique_link || link;

                this.showScreen('interview');
                this.updateConnectionStatus(false);

                if (sessionData.status === 'active' || sessionData.status === 'paused') {
                    this.elements.stopBtn.disabled = false;
                }

                this.updateAnketaStatus(sessionData.status || 'active');

                if (sessionData.dialogue_history && Array.isArray(sessionData.dialogue_history)) {
                    sessionData.dialogue_history.forEach(msg => {
                        const role = msg.role === 'assistant' ? 'ai' : 'user';
                        this.addMessage(role, msg.content);
                    });
                }

                if (sessionData.anketa_data) {
                    this.populateAnketaForm(sessionData.anketa_data);
                    this.lastServerAnketa = { ...sessionData.anketa_data };
                }

                this.startAnketaPolling();

                if (sessionData.status === 'paused') {
                    this.addMessage('ai', 'Добро пожаловать обратно! Вы можете продолжить заполнение анкеты или подтвердить её.');
                }
            }
        } catch (error) {
            LOG.error('Error resuming session:', error);
        }
    }

    // ===== Session Management =====

    async startSession() {
        LOG.info('=== START SESSION ===');
        try {
            this.elements.startBtn.disabled = true;
            this.elements.startBtn.textContent = 'Подключение...';

            // Step 1: Create session via API
            LOG.step(1, 4, 'Creating session via POST /api/session/create ...');
            const response = await fetch('/api/session/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pattern: 'interaction' }),
            });

            if (!response.ok) {
                const text = await response.text();
                LOG.error('Session create failed:', response.status, text);
                throw new Error(`Failed to create session: ${response.status}`);
            }

            const data = await response.json();
            this.sessionId = data.session_id;
            this.uniqueLink = data.unique_link;

            LOG.step(1, 4, 'Session created:');
            LOG.info('  session_id:', data.session_id);
            LOG.info('  room_name:', data.room_name);
            LOG.info('  livekit_url:', data.livekit_url);
            LOG.info('  token_length:', data.user_token ? data.user_token.length : 0);
            LOG.info('  unique_link:', data.unique_link);

            if (!data.user_token) {
                LOG.error('TOKEN IS EMPTY - LiveKit connection will fail!');
            }
            if (!data.livekit_url) {
                LOG.error('LIVEKIT_URL IS EMPTY - LiveKit connection will fail!');
            }

            // Step 2: Connect to LiveKit room
            LOG.step(2, 4, `Connecting to LiveKit room: ${data.room_name} ...`);
            await this.connectToRoom(data.livekit_url, data.user_token, data.room_name);
            LOG.step(2, 4, 'Connected to LiveKit room');

            // Step 3: Show interview screen
            LOG.step(3, 4, 'Showing interview screen');
            this.showScreen('interview');
            this.updateConnectionStatus(true);
            this.elements.stopBtn.disabled = false;
            this.updateAnketaStatus('active');

            this.addMessage('ai', 'Здравствуйте! Я помогу вам создать голосового агента для вашего бизнеса. Расскажите, чем занимается ваша компания?');

            // Step 4: Start anketa polling
            LOG.step(4, 4, 'Starting anketa polling');
            this.startAnketaPolling();

            LOG.info('=== SESSION STARTED SUCCESSFULLY ===');

            // Auto-enable microphone after connection
            LOG.info('Auto-enabling microphone in 1 second...');
            setTimeout(() => this.startRecording(), 1000);

        } catch (error) {
            LOG.error('=== SESSION START FAILED ===', error);
            this.elements.startBtn.disabled = false;
            this.elements.startBtn.textContent = 'Начать консультацию';
            alert('Ошибка подключения: ' + error.message);
        }
    }

    async connectToRoom(url, token, roomName) {
        LOG.info('connectToRoom called:', { url, roomName, tokenLength: token ? token.length : 0 });

        const { Room, RoomEvent, Track } = LivekitClient;

        this.room = new Room({
            adaptiveStream: true,
            dynacast: true,
        });
        LOG.info('Room object created');

        // ---- LiveKit Room Event Handlers (detailed) ----

        this.room.on(RoomEvent.Connected, () => {
            LOG.event('Connected', {
                roomName: this.room.name,
                localIdentity: this.room.localParticipant?.identity,
                remoteParticipants: this.room.remoteParticipants?.size || 0,
            });
            this.isConnected = true;
        });

        this.room.on(RoomEvent.Disconnected, (reason) => {
            LOG.event('Disconnected', { reason });
            this.isConnected = false;
            this.updateConnectionStatus(false);
        });

        this.room.on(RoomEvent.Reconnecting, () => {
            LOG.event('Reconnecting');
        });

        this.room.on(RoomEvent.Reconnected, () => {
            LOG.event('Reconnected');
        });

        this.room.on(RoomEvent.ParticipantConnected, (participant) => {
            LOG.event('ParticipantConnected', {
                identity: participant.identity,
                sid: participant.sid,
                isAgent: participant.identity?.includes('agent'),
            });
        });

        this.room.on(RoomEvent.ParticipantDisconnected, (participant) => {
            LOG.event('ParticipantDisconnected', {
                identity: participant.identity,
            });
        });

        this.room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
            LOG.event('TrackSubscribed', {
                trackKind: track.kind,
                trackSid: track.sid,
                participantIdentity: participant.identity,
                isAudio: track.kind === Track.Kind.Audio,
                isVideo: track.kind === Track.Kind.Video,
            });
            if (track.kind === Track.Kind.Audio) {
                LOG.info('Attaching AUDIO track from agent to DOM');

                // Clean up any existing element for this track (re-subscribe scenario)
                const existing = this.agentAudioElements.get(track.sid);
                if (existing) {
                    LOG.info('Cleaning up previous audio element for track', track.sid);
                    existing.track.detach();
                    if (existing.element.parentNode) existing.element.remove();
                    existing.element.srcObject = null;
                    this.agentAudioElements.delete(track.sid);
                }

                const audioElement = track.attach();
                audioElement.id = `agent-audio-${track.sid}`;
                audioElement.muted = false;
                audioElement.volume = 1.0;
                document.body.appendChild(audioElement);
                this.agentAudioElements.set(track.sid, { track, element: audioElement });

                // Ensure playback starts (browser autoplay policy)
                const playPromise = audioElement.play();
                if (playPromise) {
                    playPromise.then(() => {
                        LOG.info('Audio element PLAYING, muted:', audioElement.muted,
                            'volume:', audioElement.volume, 'paused:', audioElement.paused);
                    }).catch(err => {
                        LOG.error('Audio play() blocked by browser:', err.message);
                        LOG.warn('User interaction needed to unmute - click anywhere on page');
                        // Add one-time click handler to resume audio
                        const resumeAudio = () => {
                            audioElement.muted = false;
                            audioElement.play().catch(() => {});
                            LOG.info('Audio resumed after user click');
                            document.removeEventListener('click', resumeAudio);
                        };
                        document.addEventListener('click', resumeAudio);
                    });
                }
            }
        });

        this.room.on(RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
            LOG.event('TrackUnsubscribed', {
                trackKind: track.kind,
                participantIdentity: participant.identity,
            });

            // Clean up audio elements to prevent memory leaks and stale playback
            if (track.kind === Track.Kind.Audio) {
                const entry = this.agentAudioElements.get(track.sid);
                if (entry) {
                    LOG.info('Cleaning up audio element for unsubscribed track', track.sid);
                    track.detach();
                    if (entry.element.parentNode) entry.element.remove();
                    entry.element.srcObject = null;
                    this.agentAudioElements.delete(track.sid);
                }
            }
        });

        this.room.on(RoomEvent.TrackPublished, (publication, participant) => {
            LOG.event('TrackPublished', {
                trackName: publication.trackName,
                trackKind: publication.kind,
                participantIdentity: participant.identity,
            });
        });

        this.room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
            if (speakers.length > 0) {
                LOG.event('ActiveSpeakersChanged', {
                    speakers: speakers.map(s => s.identity),
                });
            }
        });

        this.room.on(RoomEvent.DataReceived, (payload, participant) => {
            LOG.event('DataReceived', {
                participantIdentity: participant?.identity,
                payloadSize: payload.byteLength,
            });
            try {
                const data = JSON.parse(new TextDecoder().decode(payload));
                LOG.info('Data message parsed:', data);
                this.handleAgentMessage(data);
            } catch (e) {
                LOG.warn('Failed to parse data message:', e);
            }
        });

        this.room.on(RoomEvent.ConnectionQualityChanged, (quality, participant) => {
            LOG.event('ConnectionQualityChanged', {
                quality,
                participantIdentity: participant.identity,
            });
        });

        this.room.on(RoomEvent.SignalConnected, () => {
            LOG.event('SignalConnected');
        });

        this.room.on(RoomEvent.MediaDevicesError, (error) => {
            LOG.error('MediaDevicesError:', error);
        });

        // ---- Connect ----
        LOG.info('Calling room.connect()...');
        try {
            await this.room.connect(url, token);
            this.localParticipant = this.room.localParticipant;
            LOG.info('room.connect() succeeded:', {
                roomName: this.room.name,
                roomSid: this.room.sid,
                localIdentity: this.localParticipant?.identity,
                state: this.room.state,
                remoteParticipants: this.room.remoteParticipants?.size || 0,
            });

            // Log all current participants
            if (this.room.remoteParticipants) {
                this.room.remoteParticipants.forEach((p, sid) => {
                    LOG.info('Remote participant already in room:', {
                        identity: p.identity,
                        sid: p.sid,
                    });
                });
            }

        } catch (error) {
            LOG.error('room.connect() FAILED:', error);
            throw error;
        }
    }

    async endSession() {
        LOG.info('=== END SESSION ===');
        try {
            this.stopAnketaPolling();

            const response = await fetch(`/api/session/${this.sessionId}/end`, {
                method: 'POST',
            });

            const data = await response.json();
            LOG.info('End session response:', data);

            if (data.unique_link) {
                this.uniqueLink = data.unique_link;
            }

            // Clean up all agent audio elements before disconnect
            this.agentAudioElements.forEach(({ track, element }) => {
                track.detach();
                if (element.parentNode) element.remove();
                element.srcObject = null;
            });
            this.agentAudioElements.clear();

            if (this.room) {
                await this.room.disconnect();
                LOG.info('Room disconnected');
            }

            this.showResults(data);

        } catch (error) {
            LOG.error('Error ending session:', error);
        }
    }

    resetSession() {
        LOG.info('=== RESET SESSION ===');
        this.stopAnketaPolling();
        this.sessionId = null;
        this.uniqueLink = null;
        this.isRecording = false;
        this.focusedField = null;
        this.localEdits = {};
        this.lastServerAnketa = {};
        this.elements.dialogueContainer.innerHTML = '';
        this.clearAnketaForm();
        this.updateProgress(0);
        this.showScreen('welcome');
        this.elements.startBtn.disabled = false;
        this.elements.startBtn.textContent = 'Начать консультацию';
        this.elements.stopBtn.disabled = true;

        if (window.location.pathname.startsWith('/session/')) {
            window.history.pushState({}, '', '/');
        }
    }

    // ===== Recording =====

    async toggleRecording() {
        if (this.isRecording) {
            await this.stopRecording();
        } else {
            await this.startRecording();
        }
    }

    async startRecording() {
        if (this.isRecording) {
            LOG.info('startRecording called but already recording, skipping');
            return;
        }
        LOG.info('=== START RECORDING (mic) ===');
        try {
            LOG.info('Creating local audio track via createLocalAudioTrack...');
            const { createLocalAudioTrack } = LivekitClient;
            this.audioTrack = await createLocalAudioTrack({
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            });
            LOG.info('LocalAudioTrack created:', {
                kind: this.audioTrack.kind,
                sid: this.audioTrack.sid,
                isMuted: this.audioTrack.isMuted,
            });

            LOG.info('Publishing audio track to room...');
            await this.localParticipant.publishTrack(this.audioTrack);
            LOG.info('Audio track PUBLISHED to room:', {
                trackSid: this.audioTrack.sid,
                isMuted: this.audioTrack.isMuted,
            });

            // Verify track is not muted
            if (this.audioTrack.isMuted) {
                LOG.warn('Track is MUTED! Trying to unmute...');
                // Try to unmute
                await this.audioTrack.unmute();
                LOG.info('Track unmuted, isMuted:', this.audioTrack.isMuted);
            }

            this.isRecording = true;
            this.elements.micBtn.classList.add('recording');
            this.elements.voiceStatus.textContent = 'Слушаю...';
            document.querySelector('.wave').classList.remove('inactive');

            LOG.info('=== MIC IS NOW LIVE ===');

            // Start audio level monitoring to verify mic is working
            this.startAudioLevelMonitor();

        } catch (error) {
            LOG.error('=== MIC START FAILED ===', error);
            alert('Не удалось получить доступ к микрофону: ' + error.message);
        }
    }

    async stopRecording() {
        LOG.info('=== STOP RECORDING (mic) ===');
        if (this.audioTrack) {
            await this.localParticipant.unpublishTrack(this.audioTrack);
            this.audioTrack.stop();
            this.audioTrack = null;
            LOG.info('Audio track unpublished and stopped');
        }

        this.isRecording = false;
        this.elements.micBtn.classList.remove('recording');
        this.elements.voiceStatus.textContent = 'Нажмите и говорите';
        document.querySelector('.wave').classList.add('inactive');

        // Stop audio level monitoring
        if (this.audioLevelInterval) {
            clearInterval(this.audioLevelInterval);
            this.audioLevelInterval = null;
        }
    }

    startAudioLevelMonitor() {
        // Get the underlying MediaStreamTrack
        if (!this.audioTrack || !this.audioTrack.mediaStreamTrack) {
            LOG.warn('Cannot monitor audio level - no mediaStreamTrack');
            return;
        }

        const mediaStreamTrack = this.audioTrack.mediaStreamTrack;
        const stream = new MediaStream([mediaStreamTrack]);

        // Create audio context for level analysis
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;

        source.connect(analyser);

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        let maxLevel = 0;
        let sampleCount = 0;

        this.audioLevelInterval = setInterval(() => {
            analyser.getByteFrequencyData(dataArray);

            // Calculate average level
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
                sum += dataArray[i];
            }
            const avgLevel = sum / dataArray.length;

            if (avgLevel > maxLevel) {
                maxLevel = avgLevel;
            }

            sampleCount++;

            // Log every 2 seconds (20 samples at 100ms interval)
            if (sampleCount % 20 === 0) {
                LOG.info(`🎤 AUDIO LEVEL: current=${avgLevel.toFixed(1)}, max=${maxLevel.toFixed(1)}, trackMuted=${this.audioTrack?.isMuted}`);

                if (maxLevel < 5) {
                    LOG.warn('⚠️ VERY LOW AUDIO - Check microphone! Is it muted in system settings?');
                }
            }
        }, 100);

        LOG.info('Audio level monitoring started');
    }

    // ===== Message Handling =====

    handleAgentMessage(data) {
        LOG.info('handleAgentMessage:', data);
        switch (data.type) {
            case 'message':
                this.addMessage('ai', data.content);
                break;
            case 'transcript':
                this.addMessage('user', data.content);
                break;
            case 'phase':
                this.updatePhase(data.phase);
                break;
            case 'progress':
                this.updateProgress(data.percentage);
                break;
            case 'complete':
                this.showResults(data);
                break;
            default:
                LOG.warn('Unknown message type:', data.type);
        }
    }

    addMessage(author, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${author}`;

        const authorSpan = document.createElement('div');
        authorSpan.className = 'author';
        authorSpan.textContent = author === 'ai' ? 'AI-Консультант' : 'Вы';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        contentDiv.textContent = content;

        messageDiv.appendChild(authorSpan);
        messageDiv.appendChild(contentDiv);

        this.elements.dialogueContainer.appendChild(messageDiv);
        this.elements.dialogueContainer.scrollTop = this.elements.dialogueContainer.scrollHeight;
    }

    // ===== Anketa Polling =====

    startAnketaPolling() {
        this.stopAnketaPolling();
        this.anketaPollingInterval = setInterval(() => {
            this.pollAnketa();
        }, 2000);
        this.pollAnketa();
    }

    stopAnketaPolling() {
        if (this.anketaPollingInterval) {
            clearInterval(this.anketaPollingInterval);
            this.anketaPollingInterval = null;
        }
    }

    async pollAnketa() {
        if (!this.sessionId) return;

        try {
            const response = await fetch(`/api/session/${this.sessionId}/anketa`);
            if (!response.ok) return;

            const data = await response.json();

            if (data.status) {
                this.updateAnketaStatus(data.status);
            }

            if (data.anketa_data) {
                this.updateAnketaFromServer(data.anketa_data);
                this.lastServerAnketa = { ...data.anketa_data };
            }
        } catch (error) {
            // Suppress polling errors to avoid console spam
        }
    }

    updateAnketaFromServer(anketaData) {
        this.anketaFields.forEach(fieldName => {
            if (this.focusedField === fieldName) return;
            if (this.localEdits[fieldName]) return;

            const element = document.getElementById(`anketa-${fieldName}`);
            if (!element) return;

            const serverValue = anketaData[fieldName];
            let displayValue = '';

            if (serverValue !== null && serverValue !== undefined) {
                if (this.arrayFields.has(fieldName) && Array.isArray(serverValue)) {
                    displayValue = serverValue.join('\n');
                } else {
                    displayValue = String(serverValue);
                }
            }

            if (element.value !== displayValue) {
                element.value = displayValue;
                element.classList.add('field-updated');
                setTimeout(() => {
                    element.classList.remove('field-updated');
                }, 1500);
            }
        });
    }

    populateAnketaForm(anketaData) {
        this.anketaFields.forEach(fieldName => {
            const element = document.getElementById(`anketa-${fieldName}`);
            if (!element) return;

            const value = anketaData[fieldName];
            if (value !== null && value !== undefined) {
                if (this.arrayFields.has(fieldName) && Array.isArray(value)) {
                    element.value = value.join('\n');
                } else {
                    element.value = String(value);
                }
            }
        });
    }

    clearAnketaForm() {
        this.anketaFields.forEach(fieldName => {
            const element = document.getElementById(`anketa-${fieldName}`);
            if (element) {
                element.value = '';
            }
        });
        this.updateAnketaStatus('');
    }

    // ===== Anketa Saving (Debounced) =====

    scheduleAnketaSave() {
        if (this.anketaSaveTimeout) {
            clearTimeout(this.anketaSaveTimeout);
        }
        this.anketaSaveTimeout = setTimeout(() => {
            this.saveAnketa();
        }, 1000);
    }

    async saveAnketa() {
        if (!this.sessionId) return;

        const anketaData = this.collectAnketaData();

        try {
            const response = await fetch(`/api/session/${this.sessionId}/anketa`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ anketa_data: anketaData }),
            });

            if (response.ok) {
                this.localEdits = {};
                this.lastServerAnketa = { ...anketaData };
            }
        } catch (error) {
            LOG.error('Error saving anketa:', error);
        }
    }

    collectAnketaData() {
        const data = {};
        this.anketaFields.forEach(fieldName => {
            const element = document.getElementById(`anketa-${fieldName}`);
            if (!element) return;

            const rawValue = element.value.trim();
            if (this.arrayFields.has(fieldName)) {
                data[fieldName] = rawValue
                    ? rawValue.split('\n').map(s => s.trim()).filter(s => s.length > 0)
                    : [];
            } else {
                data[fieldName] = rawValue || '';
            }
        });
        return data;
    }

    // ===== Anketa Actions =====

    async confirmAnketa() {
        if (!this.sessionId) return;

        if (this.anketaSaveTimeout) {
            clearTimeout(this.anketaSaveTimeout);
        }
        await this.saveAnketa();

        try {
            const response = await fetch(`/api/session/${this.sessionId}/confirm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });

            if (response.ok) {
                this.updateAnketaStatus('confirmed');
                this.addMessage('ai', 'Анкета подтверждена! Спасибо. Мы свяжемся с вами в ближайшее время.');
                this.elements.confirmAnketaBtn.disabled = true;
                this.elements.confirmAnketaBtn.textContent = 'Подтверждено';
            } else {
                alert('Ошибка при подтверждении анкеты.');
            }
        } catch (error) {
            LOG.error('Error confirming anketa:', error);
            alert('Ошибка при подтверждении анкеты.');
        }
    }

    async saveAndLeave() {
        if (!this.sessionId) return;

        if (this.anketaSaveTimeout) {
            clearTimeout(this.anketaSaveTimeout);
        }
        await this.saveAnketa();

        try {
            const response = await fetch(`/api/session/${this.sessionId}/end`, {
                method: 'POST',
            });

            const data = await response.json();
            const link = data.unique_link || this.uniqueLink;

            this.stopAnketaPolling();

            if (this.room) {
                await this.room.disconnect();
            }

            const fullLink = `${window.location.origin}/session/${link}`;
            this.elements.dialogueContainer.innerHTML = '';
            this.addMessage('ai',
                `Сессия сохранена. Вы можете вернуться по ссылке:\n${fullLink}\n\nСсылка также скопирована в буфер обмена.`
            );

            this.copyToClipboard(fullLink);
            this.updateAnketaStatus('paused');
            this.updateConnectionStatus(false);

        } catch (error) {
            LOG.error('Error saving and leaving:', error);
            alert('Ошибка сохранения сессии.');
        }
    }

    async copySessionLink() {
        const link = this.uniqueLink;
        if (!link) {
            alert('Ссылка ещё не доступна. Начните сессию.');
            return;
        }

        const fullLink = `${window.location.origin}/session/${link}`;
        const success = await this.copyToClipboard(fullLink);

        if (success) {
            this.elements.copyLinkBtn.textContent = 'Скопировано!';
            this.elements.copyLinkBtn.classList.add('copied');
            setTimeout(() => {
                this.elements.copyLinkBtn.textContent = 'Копировать ссылку';
                this.elements.copyLinkBtn.classList.remove('copied');
            }, 2000);
        } else {
            prompt('Скопируйте ссылку:', fullLink);
        }
    }

    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (error) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                return true;
            } catch (e) {
                return false;
            } finally {
                document.body.removeChild(textarea);
            }
        }
    }

    // ===== Anketa Status =====

    updateAnketaStatus(status) {
        const badge = this.elements.anketaStatusBadge;
        if (!badge) return;

        badge.className = 'anketa-status-badge';

        const statusLabels = {
            'active': 'активна',
            'paused': 'пауза',
            'reviewing': 'на проверке',
            'confirmed': 'подтверждена',
            'declined': 'отклонена',
        };

        badge.textContent = statusLabels[status] || 'ожидание';

        if (status) {
            badge.classList.add(`status-${status}`);
        }
    }

    // ===== UI Updates =====

    showScreen(screenName) {
        Object.values(this.screens).forEach(screen => {
            screen.classList.remove('active');
        });
        this.screens[screenName].classList.add('active');
    }

    updateConnectionStatus(connected) {
        const status = this.elements.connectionStatus;
        if (connected) {
            status.classList.add('connected');
            status.querySelector('.text').textContent = 'Подключен';
        } else {
            status.classList.remove('connected');
            status.querySelector('.text').textContent = 'Не подключен';
        }
    }

    updatePhase(phase) {
        const phaseNames = {
            discovery: 'Знакомство',
            analysis: 'Анализ',
            proposal: 'Предложение',
            refinement: 'Анкета',
        };

        this.elements.phaseIndicator.querySelector('.phase').textContent =
            phaseNames[phase] || phase;
    }

    updateProgress(percentage) {
        this.elements.progressFill.style.width = `${percentage}%`;
        this.elements.progressText.textContent = `${Math.round(percentage)}% заполнено`;
    }

    showResults(data) {
        this.stopAnketaPolling();

        this.elements.resultsStats.innerHTML = `
            <p><span>Длительность:</span><span>${Math.round(data.duration / 60)} мин</span></p>
            <p><span>Сообщений:</span><span>${data.message_count || 0}</span></p>
            <p><span>Полей заполнено:</span><span>${data.fields_filled || 0}</span></p>
        `;

        if (data.files) {
            this.elements.resultsFiles.innerHTML = `
                <a href="${data.files.json}" download>Скачать JSON</a>
                <a href="${data.files.markdown}" download>Скачать Markdown</a>
            `;
        }

        if (this.uniqueLink || data.unique_link) {
            const link = data.unique_link || this.uniqueLink;
            const fullLink = `${window.location.origin}/session/${link}`;
            this.elements.resultsFiles.innerHTML += `
                <div class="return-link-section">
                    <p style="color: var(--text-muted); margin-top: 1rem; font-size: 0.875rem;">
                        Ссылка для возврата к сессии:
                    </p>
                    <a href="${fullLink}" style="word-break: break-all;">${fullLink}</a>
                </div>
            `;
        }

        this.showScreen('results');
    }
}

// Инициализация приложения
document.addEventListener('DOMContentLoaded', () => {
    LOG.info('DOM loaded, creating app...');
    window.app = new VoiceInterviewerApp();
});
