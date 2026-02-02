/**
 * Voice Interviewer Web UI
 * Клиентское приложение для голосового взаимодействия
 */

class VoiceInterviewerApp {
    constructor() {
        // LiveKit
        this.room = null;
        this.localParticipant = null;
        this.audioTrack = null;

        // State
        this.sessionId = null;
        this.isRecording = false;
        this.isConnected = false;

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
        };

        // Screens
        this.screens = {
            welcome: document.getElementById('welcome-screen'),
            interview: document.getElementById('interview-screen'),
            results: document.getElementById('results-screen'),
        };

        this.init();
    }

    init() {
        // Event listeners
        this.elements.startBtn.addEventListener('click', () => this.startSession());
        this.elements.micBtn.addEventListener('click', () => this.toggleRecording());
        this.elements.stopBtn.addEventListener('click', () => this.endSession());
        this.elements.newBtn.addEventListener('click', () => this.resetSession());
    }

    // ===== Session Management =====

    async startSession() {
        try {
            this.elements.startBtn.disabled = true;
            this.elements.startBtn.textContent = 'Подключение...';

            // Создаём сессию через API
            const response = await fetch('/api/session/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pattern: 'interaction' }),
            });

            if (!response.ok) {
                throw new Error('Failed to create session');
            }

            const data = await response.json();
            this.sessionId = data.session_id;

            // Подключаемся к LiveKit
            await this.connectToRoom(data.livekit_url, data.user_token, data.room_name);

            // Показываем экран интервью
            this.showScreen('interview');
            this.updateConnectionStatus(true);

            // Добавляем приветственное сообщение
            this.addMessage('ai', 'Здравствуйте! Я помогу вам создать голосового агента для вашего бизнеса. Расскажите, чем занимается ваша компания?');

        } catch (error) {
            console.error('Error starting session:', error);
            this.elements.startBtn.disabled = false;
            this.elements.startBtn.textContent = 'Начать консультацию';
            alert('Ошибка подключения. Проверьте соединение.');
        }
    }

    async connectToRoom(url, token, roomName) {
        const { Room, RoomEvent, Track } = LivekitClient;

        this.room = new Room({
            adaptiveStream: true,
            dynacast: true,
        });

        // Event handlers
        this.room.on(RoomEvent.Connected, () => {
            console.log('Connected to room');
            this.isConnected = true;
        });

        this.room.on(RoomEvent.Disconnected, () => {
            console.log('Disconnected from room');
            this.isConnected = false;
            this.updateConnectionStatus(false);
        });

        this.room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
            if (track.kind === Track.Kind.Audio) {
                // Воспроизводим аудио от агента
                const audioElement = track.attach();
                document.body.appendChild(audioElement);
            }
        });

        this.room.on(RoomEvent.DataReceived, (payload, participant) => {
            // Получаем сообщения от агента
            const data = JSON.parse(new TextDecoder().decode(payload));
            this.handleAgentMessage(data);
        });

        // Подключаемся
        await this.room.connect(url, token);
        this.localParticipant = this.room.localParticipant;
    }

    async endSession() {
        try {
            // Отправляем запрос на завершение
            const response = await fetch(`/api/session/${this.sessionId}/end`, {
                method: 'POST',
            });

            const data = await response.json();

            // Отключаемся от комнаты
            if (this.room) {
                await this.room.disconnect();
            }

            // Показываем результаты
            this.showResults(data);

        } catch (error) {
            console.error('Error ending session:', error);
        }
    }

    resetSession() {
        this.sessionId = null;
        this.isRecording = false;
        this.elements.dialogueContainer.innerHTML = '';
        this.updateProgress(0);
        this.showScreen('welcome');
        this.elements.startBtn.disabled = false;
        this.elements.startBtn.textContent = 'Начать консультацию';
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
        try {
            // Запрашиваем доступ к микрофону
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // Публикуем аудио трек
            const { LocalAudioTrack } = LivekitClient;
            this.audioTrack = new LocalAudioTrack(stream.getAudioTracks()[0]);

            await this.localParticipant.publishTrack(this.audioTrack);

            this.isRecording = true;
            this.elements.micBtn.classList.add('recording');
            this.elements.voiceStatus.textContent = 'Слушаю...';
            document.querySelector('.wave').classList.remove('inactive');

        } catch (error) {
            console.error('Error starting recording:', error);
            alert('Не удалось получить доступ к микрофону');
        }
    }

    async stopRecording() {
        if (this.audioTrack) {
            await this.localParticipant.unpublishTrack(this.audioTrack);
            this.audioTrack.stop();
            this.audioTrack = null;
        }

        this.isRecording = false;
        this.elements.micBtn.classList.remove('recording');
        this.elements.voiceStatus.textContent = 'Нажмите и говорите';
        document.querySelector('.wave').classList.add('inactive');
    }

    // ===== Message Handling =====

    handleAgentMessage(data) {
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
        // Статистика
        this.elements.resultsStats.innerHTML = `
            <p><span>Длительность:</span><span>${Math.round(data.duration / 60)} мин</span></p>
            <p><span>Сообщений:</span><span>${data.message_count || 0}</span></p>
            <p><span>Полей заполнено:</span><span>${data.fields_filled || 0}</span></p>
        `;

        // Файлы
        if (data.files) {
            this.elements.resultsFiles.innerHTML = `
                <a href="${data.files.json}" download>📄 Скачать JSON</a>
                <a href="${data.files.markdown}" download>📝 Скачать Markdown</a>
            `;
        }

        this.showScreen('results');
    }
}

// Инициализация приложения
document.addEventListener('DOMContentLoaded', () => {
    window.app = new VoiceInterviewerApp();
});
