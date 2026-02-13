/**
 * Hanc.AI Voice Consultant — Web UI
 * Dashboard + Session management + Voice interview
 */

const LOG = {
    info: (...args) => console.log('%c[HANC]', 'color: #2563eb; font-weight: bold', ...args),
    warn: (...args) => console.warn('%c[HANC]', 'color: #d97706; font-weight: bold', ...args),
    error: (...args) => console.error('%c[HANC]', 'color: #dc2626; font-weight: bold', ...args),
    event: (name, data) => console.log(
        `%c[HANC EVENT: ${name}]`, 'color: #7c3aed; font-weight: bold', data || ''
    ),
};


// =====================================================================
// Simple Router
// =====================================================================

class Router {
    constructor(app) {
        this.app = app;
        window.addEventListener('popstate', () => this.resolve());
    }

    navigate(path) {
        window.history.pushState({}, '', path);
        this.resolve();
    }

    resolve() {
        const path = window.location.pathname;

        // /session/:link/review
        let match = path.match(/^\/session\/([a-f0-9-]+)\/review$/i);
        if (match) {
            this.app.showSessionReview(match[1]);
            return;
        }

        // /session/:link
        match = path.match(/^\/session\/([a-f0-9-]+)$/i);
        if (match) {
            this.app.showSession(match[1]);
            return;
        }

        // / (dashboard)
        this.app.showDashboard();
    }
}


// =====================================================================
// Toast notifications (replaces alert/confirm)
// =====================================================================

function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-fade');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// =====================================================================
// Main Application
// =====================================================================

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
        this.isPaused = false;
        this.isConnected = false;
        this.agentAudioElements = new Map();

        // Anketa state
        this.anketaPollingInterval = null;
        this.anketaSaveTimeout = null;
        this.focusedField = null;
        this.localEdits = {};
        this.consultationType = 'consultation'; // 'consultation' or 'interview'
        this.lastServerAnketa = {};
        this.messageCount = 0;
        this.roomName = null;
        this._lastFieldCount = 0;
        this._lastPct = 0;
        this._agentSpoke = false;
        this.isAnketaEditable = false; // v5.5: Anketa edit mode state

        // SPRINT 5: Debug mode
        this.debugMode = localStorage.getItem('anketa_debug') === 'true' || window.location.search.includes('debug=true');
        if (this.debugMode) {
            console.log('[DEBUG MODE] Anketa debugging enabled');
            this._initDebugPanel();
        }

        // Dashboard state
        this.currentFilter = '';

        // Settings lock — settings that cannot change mid-session
        this._lockedSettings = ['voice_gender', 'consultation_type', 'llm_provider'];
        this._sessionOriginalConfig = null;
        this._pushLiveSettingsTimer = null;

        // Anketa field definitions — matches FinalAnketa v2.0 schema
        this.anketaFields = [
            'company_name', 'contact_name', 'contact_role', 'phone', 'email', 'website',
            'industry', 'specialization', 'business_type', 'company_description',
            'services', 'client_types', 'current_problems', 'business_goals',
            'agent_name', 'agent_purpose', 'agent_tasks',
            'integrations', 'voice_gender', 'voice_tone', 'call_direction',
            'transfer_conditions',
            'constraints', 'compliance_requirements',
            'call_volume', 'budget', 'timeline', 'additional_notes'
        ];

        this.arrayFields = new Set([
            'services', 'client_types', 'current_problems', 'business_goals',
            'agent_tasks', 'integrations', 'transfer_conditions',
            'constraints', 'compliance_requirements'
        ]);

        // v5.4: Section definitions for stepper pipeline
        this.sectionDefs = [
            { id: 'contacts', label: 'Знакомство',
              fields: ['company_name','contact_name','contact_role','phone','email','website'] },
            { id: 'business', label: 'Бизнес',
              fields: ['industry','specialization','business_type','company_description',
                       'services','client_types','current_problems','business_goals'] },
            { id: 'agent', label: 'Решение',
              fields: ['agent_name','call_direction','agent_purpose','agent_tasks',
                       'integrations','voice_gender','voice_tone','transfer_conditions'] },
            { id: 'additional', label: 'Детали',
              fields: ['constraints','compliance_requirements','call_volume','budget',
                       'timeline','additional_notes'] },
        ];
        this._userScrolling = false;
        this._userScrollTimer = null;
        this._scrollDebounceTimer = null;
        this._previousFieldValues = {};

        this.aiBlocks = [
            { key: 'faq_items', label: 'FAQ' },
            { key: 'objection_handlers', label: 'Возражения' },
            { key: 'sample_dialogue', label: 'Пример диалога' },
            { key: 'financial_metrics', label: 'Финмодель' },
            { key: 'competitors', label: 'Конкуренты' },
            { key: 'market_insights', label: 'Рынок' },
            { key: 'escalation_rules', label: 'Эскалация' },
            { key: 'success_kpis', label: 'KPI' },
            { key: 'launch_checklist', label: 'Чеклист' },
            { key: 'ai_recommendations', label: 'Рекомендации' },
        ];

        // DOM Elements
        this.elements = {
            newSessionBtn: document.getElementById('new-session-btn'),
            logoLink: document.getElementById('logo-link'),
            // Interview
            backBtn: document.getElementById('back-to-dashboard'),
            micBtn: document.getElementById('mic-btn'),
            pauseBtn: document.getElementById('pause-btn'),
            connectionStatus: document.getElementById('connection-status'),
            sessionCompany: document.getElementById('session-company'),
            progressFill: document.getElementById('progress-fill'),
            progressText: document.getElementById('progress-text'),
            dialogueContainer: document.getElementById('dialogue-container'),
            voiceIndicator: document.getElementById('voice-indicator'),
            voiceStatus: document.getElementById('voice-status'),
            // Anketa
            anketaForm: document.getElementById('anketa-form'),
            anketaStatusBadge: document.getElementById('anketa-status-badge'),
            confirmAnketaBtn: document.getElementById('confirm-anketa-btn'),
            saveLeaveBtn: document.getElementById('save-leave-btn'),
            copyLinkBtn: document.getElementById('copy-link-btn'),
            // Document upload
            docUploadBtn: document.getElementById('doc-upload-btn'),
            docUploadInput: document.getElementById('doc-upload-input'),
            docUploadStatus: document.getElementById('doc-upload-status'),
            // Voice settings
            silenceSlider: document.getElementById('silence-slider'),
            silenceValue: document.getElementById('silence-value'),
            speedSlider: document.getElementById('speed-slider'),
            speedValue: document.getElementById('speed-value'),
            // Review
            reviewBackBtn: document.getElementById('review-back-btn'),
            reviewResumeBtn: document.getElementById('review-resume-btn'),
            reviewCopyLinkBtn: document.getElementById('review-copy-link-btn'),
            // Quick settings
            quickSettingsBtn: document.getElementById('quick-settings-btn'),
            quickSettingsPanel: document.getElementById('quick-settings-panel'),
            speedSliderQuick: document.getElementById('speed-slider-quick'),
            speedValueQuick: document.getElementById('speed-value-quick'),
            silenceSliderQuick: document.getElementById('silence-slider-quick'),
            silenceValueQuick: document.getElementById('silence-value-quick'),
        };

        // Screens
        this.screens = {
            landing: document.getElementById('landing-screen'),
            dashboard: document.getElementById('dashboard-screen'),
            session: document.getElementById('session-screen'),
            review: document.getElementById('review-screen'),
        };

        this.init();
        LOG.info('=== VoiceInterviewerApp ready ===');
    }

    // SPRINT 5: Debug panel for anketa monitoring
    _initDebugPanel() {
        const debugPanel = document.createElement('div');
        debugPanel.id = 'anketa-debug-panel';
        debugPanel.innerHTML = `
            <div style="position: fixed; bottom: 10px; left: 10px; background: rgba(0,0,0,0.85); color: white; padding: 12px; border-radius: 6px; font-size: 12px; font-family: monospace; z-index: 10000; min-width: 280px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                <div style="font-weight: bold; margin-bottom: 8px; color: #4ade80;">⚙️ Anketa Debug</div>
                <div id="debug-completion" style="margin-bottom: 4px;">Completion: 0%</div>
                <div id="debug-fields" style="margin-bottom: 4px;">Fields: 0/28</div>
                <div id="debug-messages" style="margin-bottom: 4px;">Messages: 0</div>
                <div id="debug-polling" style="margin-bottom: 4px;">Polling: <span style="color: #4ade80;">active</span></div>
                <div id="debug-errors" style="color: #fbbf24;">Errors: 0</div>
                <button id="debug-close-btn" style="margin-top: 8px; padding: 4px 8px; background: #374151; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px;">Close</button>
            </div>
        `;
        document.body.appendChild(debugPanel);

        // Close button
        document.getElementById('debug-close-btn')?.addEventListener('click', () => {
            debugPanel.remove();
            this.debugMode = false;
            localStorage.removeItem('anketa_debug');
        });

        LOG.info('[DEBUG] Debug panel initialized');
    }

    _updateDebugPanel(completion, filledCount, totalFields, messageCount, pollingActive = true) {
        if (!this.debugMode) return;

        const completionEl = document.getElementById('debug-completion');
        const fieldsEl = document.getElementById('debug-fields');
        const messagesEl = document.getElementById('debug-messages');
        const pollingEl = document.getElementById('debug-polling');
        const errorsEl = document.getElementById('debug-errors');

        if (completionEl) completionEl.textContent = `Completion: ${Math.round(completion)}%`;
        if (fieldsEl) fieldsEl.textContent = `Fields: ${filledCount}/${totalFields}`;
        if (messagesEl) messagesEl.textContent = `Messages: ${messageCount}`;
        if (pollingEl) {
            pollingEl.innerHTML = pollingActive
                ? 'Polling: <span style="color: #4ade80;">active</span>'
                : 'Polling: <span style="color: #ef4444;">stopped</span>';
        }
        if (errorsEl && this._pollingFailureCount) {
            errorsEl.textContent = `Errors: ${this._pollingFailureCount}`;
        }
    }

    init() {
        // Header — logo: always soft-navigate to home (session stays alive)
        this.elements.logoLink.addEventListener('click', (e) => {
            e.preventDefault();
            this.goBackToDashboard();
        });
        // Header — nav links
        document.getElementById('nav-about')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.showScreen('landing');
        });
        document.getElementById('nav-sessions')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.goBackToDashboard();
        });
        this.elements.newSessionBtn.addEventListener('click', () => this._showPreSession(this.consultationType || 'consultation'));

        // Auth button (placeholder)
        document.getElementById('auth-btn')?.addEventListener('click', () => {
            showToast('Авторизация в разработке', 'info', 2500);
        });

        // Interview controls
        this.elements.backBtn.addEventListener('click', () => this.goBackToDashboard());
        this.elements.micBtn.addEventListener('click', () => this.toggleRecording());
        this.elements.pauseBtn.addEventListener('click', () => this.togglePause());

        // Session controls (Level 1 - Global)
        const btnAllSessions = document.getElementById('btn-all-sessions');
        const btnStopSession = document.getElementById('btn-stop-session');
        const btnStartSession = document.getElementById('btn-start-session');
        const btnRecordSession = document.getElementById('btn-record-session');
        const btnGoToResults = document.getElementById('btn-go-to-results');

        if (btnAllSessions) {
            btnAllSessions.addEventListener('click', () => this.handleAllSessions());
        }
        if (btnStopSession) {
            btnStopSession.addEventListener('click', () => this.handleStopSession());
        }
        if (btnStartSession) {
            btnStartSession.addEventListener('click', () => this.handleStartSession());
        }
        if (btnRecordSession) {
            btnRecordSession.addEventListener('click', () => this.handleRecordSession());
        }
        if (btnGoToResults) {
            btnGoToResults.addEventListener('click', () => this.handleGoToResults());
        }

        // Anketa actions
        this.elements.confirmAnketaBtn.addEventListener('click', () => this.confirmAnketa());
        this.elements.saveLeaveBtn.addEventListener('click', () => this.saveAndLeave());
        this.elements.copyLinkBtn.addEventListener('click', () => this.copySessionLink());

        // Anketa edit/save controls (Level 3)
        const btnEditAnketa = document.getElementById('btn-edit-anketa');
        const btnSaveAnketa = document.getElementById('btn-save-anketa');
        const anketaFieldset = document.getElementById('anketa-fieldset');

        if (btnEditAnketa && btnSaveAnketa && anketaFieldset) {
            btnEditAnketa.addEventListener('click', () => {
                this.isAnketaEditable = true;
                anketaFieldset.disabled = false;
                btnEditAnketa.style.display = 'none';
                btnSaveAnketa.style.display = 'flex';
            });

            btnSaveAnketa.addEventListener('click', async () => {
                await this.handleSaveAnketa();
                this.isAnketaEditable = false;
                anketaFieldset.disabled = true;
                btnEditAnketa.style.display = 'flex';
                btnSaveAnketa.style.display = 'none';
            });
        }

        // Document upload
        if (this.elements.docUploadBtn && this.elements.docUploadInput) {
            this.elements.docUploadBtn.addEventListener('click', () => {
                this.elements.docUploadInput.click();
            });
            this.elements.docUploadInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.uploadDocuments(e.target.files);
                }
            });
        }

        // Voice settings sliders
        if (this.elements.silenceSlider) {
            this.elements.silenceSlider.addEventListener('input', (e) => {
                this.elements.silenceValue.textContent = (e.target.value / 1000).toFixed(1);
            });
        }
        if (this.elements.speedSlider) {
            this.elements.speedSlider.addEventListener('input', (e) => {
                this.elements.speedValue.textContent = (e.target.value / 100).toFixed(1);
            });
        }

        // Restore settings from localStorage
        this._restoreSettings();

        // Check available LLM providers and disable unavailable ones
        this._loadAvailableProviders();

        // Persist settings on change + sync to quick panel + push live if active session
        document.querySelectorAll('.segment-control input[type="radio"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this._persistSettings();
                // Sync editable settings to quick panel
                if (radio.name === 'verbosity') {
                    const qr = document.querySelector(`input[name="verbosity_quick"][value="${radio.value}"]`);
                    if (qr) qr.checked = true;
                }
                // Push live for editable settings during active session
                if (this.sessionId && !this._lockedSettings.includes(radio.name)) {
                    this._pushLiveSettings();
                }
            });
        });
        if (this.elements.silenceSlider) {
            this.elements.silenceSlider.addEventListener('change', () => {
                this._persistSettings();
                // Sync to quick panel
                if (this.elements.silenceSliderQuick) {
                    this.elements.silenceSliderQuick.value = this.elements.silenceSlider.value;
                    this.elements.silenceValueQuick.textContent = this.elements.silenceValue.textContent;
                }
                if (this.sessionId) this._pushLiveSettings();
            });
        }
        if (this.elements.speedSlider) {
            this.elements.speedSlider.addEventListener('change', () => {
                this._persistSettings();
                // Sync to quick panel
                if (this.elements.speedSliderQuick) {
                    this.elements.speedSliderQuick.value = this.elements.speedSlider.value;
                    this.elements.speedValueQuick.textContent = this.elements.speedValue.textContent;
                }
                if (this.sessionId) this._pushLiveSettings();
            });
        }

        // Dashboard filters
        document.getElementById('filter-tabs')?.addEventListener('click', (e) => {
            const btn = e.target.closest('.filter-tab');
            if (!btn) return;
            document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            this.currentFilter = btn.dataset.status || '';
            this.loadSessions(this.currentFilter);
        });

        // Review
        this.elements.reviewBackBtn?.addEventListener('click', () => this.router.navigate('/'));
        this.elements.reviewResumeBtn?.addEventListener('click', () => {
            if (this._reviewLink) this.router.navigate(`/session/${this._reviewLink}`);
        });
        this.elements.reviewCopyLinkBtn?.addEventListener('click', () => {
            if (this._reviewLink) {
                this.copyToClipboard(`${window.location.origin}/session/${this._reviewLink}`);
                showToast('Ссылка скопирована');
            }
        });

        this.setupAnketaFieldListeners();

        // Quick settings panel
        this._initQuickSettings();

        // Click on locked settings → toast
        document.querySelectorAll('[data-lockable]').forEach(el => {
            el.addEventListener('click', (e) => {
                if (el.classList.contains('segment-control--locked')) {
                    e.preventDefault();
                    e.stopPropagation();
                    const setting = el.dataset.setting;
                    const labels = {
                        voice_gender: 'Голос нельзя изменить во время сессии',
                        consultation_type: 'Тип консультации нельзя изменить во время сессии',
                        llm_provider: 'LLM модель нельзя изменить во время сессии',
                    };
                    showToast(labels[setting] || 'Настройка заблокирована на время сессии', 'info', 2000);
                }
            });
        });

        // Warn on tab close during active session + save anketa via sendBeacon
        window.addEventListener('beforeunload', (e) => {
            if (this.sessionId && this.isRecording) {
                e.preventDefault();
                e.returnValue = '';
                // Best-effort save via sendBeacon (works even when tab is closing)
                if (this.consultationType !== 'interview') {
                    const anketaData = {};
                    this.anketaFields.forEach(fieldName => {
                        const el = document.getElementById(`anketa-${fieldName}`);
                        if (!el) return;
                        const rawValue = el.value.trim();
                        if (this.arrayFields.has(fieldName)) {
                            anketaData[fieldName] = rawValue
                                ? rawValue.split('\n').map(s => s.trim()).filter(s => s.length > 0)
                                : [];
                        } else {
                            anketaData[fieldName] = rawValue || '';
                        }
                    });
                    const hasData = Object.values(anketaData).some(v =>
                        Array.isArray(v) ? v.length > 0 : v !== ''
                    );
                    if (hasData) {
                        navigator.sendBeacon(
                            `/api/session/${this.sessionId}/anketa`,
                            new Blob([JSON.stringify({ anketa_data: anketaData })], { type: 'application/json' })
                        );
                    }
                }
            }
        });

        // Init router — must be last
        this.router = new Router(this);
        this.router.resolve();
    }

    // ===== Voice Settings =====

    getVoiceSettings() {
        const settings = {
            speech_speed: parseFloat(this.elements.speedSlider?.value || '100') / 100,
            silence_duration_ms: parseInt(this.elements.silenceSlider?.value || '2000', 10),
            voice_gender: document.querySelector('input[name="voice_gender"]:checked')?.value || 'neutral',
            consultation_type: this.consultationType || 'consultation',
            verbosity: document.querySelector('input[name="verbosity"]:checked')?.value || 'normal',
            llm_provider: document.querySelector('input[name="llm_provider"]:checked')?.value || 'deepseek',
        };

        // Guard: if session is active, force locked settings to original values
        if (this.sessionId && this._sessionOriginalConfig) {
            for (const key of this._lockedSettings) {
                if (this._sessionOriginalConfig[key] !== undefined) {
                    settings[key] = this._sessionOriginalConfig[key];
                }
            }
        }

        return settings;
    }

    _persistSettings() {
        try {
            localStorage.setItem('hanc_voice_settings', JSON.stringify(this.getVoiceSettings()));
        } catch {}
    }

    _restoreSettings() {
        try {
            const saved = JSON.parse(localStorage.getItem('hanc_voice_settings'));
            if (!saved) return;

            // Restore sliders
            if (saved.silence_duration_ms && this.elements.silenceSlider) {
                this.elements.silenceSlider.value = saved.silence_duration_ms;
                this.elements.silenceValue.textContent = (saved.silence_duration_ms / 1000).toFixed(1);
            }
            if (saved.speech_speed && this.elements.speedSlider) {
                this.elements.speedSlider.value = Math.round(saved.speech_speed * 100);
                this.elements.speedValue.textContent = saved.speech_speed.toFixed(1);
            }

            // Restore radio buttons
            for (const name of ['voice_gender', 'verbosity', 'llm_provider']) {
                if (saved[name]) {
                    const radio = document.querySelector(`input[name="${name}"][value="${saved[name]}"]`);
                    if (radio) radio.checked = true;
                }
            }
        } catch {}
    }

    // ===== Pre-Session Flow =====

    async startWithMode(mode) {
        if (this._startingMode) return;
        this._startingMode = true;
        try {
            localStorage.setItem('hasVisited', '1');
            this.consultationType = mode;
            this._showPreSession(mode);
        } finally {
            this._startingMode = false;
        }
    }

    _showPreSession(mode) {
        const badge = document.getElementById('session-mode-badge');
        if (badge) {
            badge.textContent = mode === 'interview' ? 'Интервью' : 'Консультация';
            badge.classList.toggle('badge-interview', mode === 'interview');
        }
        document.getElementById('session-screen').classList.remove('voice-active');
        this.showScreen('session');
        this._restoreSettings();
    }

    async _startVoiceFromPreSession() {
        if (this._isCreatingSession) return;
        this._persistSettings();
        const startBtn = document.querySelector('.btn-start-voice');
        if (startBtn) { startBtn.disabled = true; startBtn.textContent = 'Подключение...'; }
        document.getElementById('session-screen').classList.add('voice-active');
        try {
            await this.createAndGoToSession();
        } finally {
            if (startBtn) { startBtn.disabled = false; startBtn.textContent = 'Начать разговор'; }
        }
    }

    // ===== Settings Lock & Quick Settings =====

    _updateSettingsLockState() {
        const hasSession = !!this.sessionId;
        const banner = document.getElementById('settings-lock-banner');

        // Banner visibility
        if (banner) banner.classList.toggle('visible', hasSession);

        // Lock/unlock fieldsets
        document.querySelectorAll('[data-lockable]').forEach(el => {
            el.classList.toggle('segment-control--locked', hasSession);
        });

        // Live badges visibility
        document.querySelectorAll('.setting-live-badge').forEach(el => {
            el.classList.toggle('visible', hasSession);
        });
    }

    _initQuickSettings() {
        const btn = this.elements.quickSettingsBtn;
        const panel = this.elements.quickSettingsPanel;
        if (!btn || !panel) return;

        // Toggle panel
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = panel.classList.contains('visible');
            panel.classList.toggle('visible', !isOpen);
            btn.classList.toggle('active', !isOpen);
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!panel.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
                panel.classList.remove('visible');
                btn.classList.remove('active');
            }
        });

        // Quick speed slider
        if (this.elements.speedSliderQuick) {
            this.elements.speedSliderQuick.addEventListener('input', (e) => {
                const val = e.target.value;
                this.elements.speedValueQuick.textContent = (val / 100).toFixed(1);
                // Sync to dashboard slider
                if (this.elements.speedSlider) {
                    this.elements.speedSlider.value = val;
                    this.elements.speedValue.textContent = (val / 100).toFixed(1);
                }
                this._pushLiveSettings();
            });
        }

        // Quick silence slider
        if (this.elements.silenceSliderQuick) {
            this.elements.silenceSliderQuick.addEventListener('input', (e) => {
                const val = e.target.value;
                this.elements.silenceValueQuick.textContent = (val / 1000).toFixed(1);
                // Sync to dashboard slider
                if (this.elements.silenceSlider) {
                    this.elements.silenceSlider.value = val;
                    this.elements.silenceValue.textContent = (val / 1000).toFixed(1);
                }
                this._pushLiveSettings();
            });
        }

        // Quick verbosity radios
        document.querySelectorAll('input[name="verbosity_quick"]').forEach(radio => {
            radio.addEventListener('change', () => {
                // Sync to dashboard
                const dashRadio = document.querySelector(`input[name="verbosity"][value="${radio.value}"]`);
                if (dashRadio) dashRadio.checked = true;
                this._pushLiveSettings();
            });
        });
    }

    _syncQuickSettings() {
        // Copy current dashboard values to quick settings panel
        if (this.elements.speedSliderQuick && this.elements.speedSlider) {
            this.elements.speedSliderQuick.value = this.elements.speedSlider.value;
            this.elements.speedValueQuick.textContent = this.elements.speedValue.textContent;
        }
        if (this.elements.silenceSliderQuick && this.elements.silenceSlider) {
            this.elements.silenceSliderQuick.value = this.elements.silenceSlider.value;
            this.elements.silenceValueQuick.textContent = this.elements.silenceValue.textContent;
        }
        const currentVerbosity = document.querySelector('input[name="verbosity"]:checked')?.value || 'normal';
        const quickRadio = document.querySelector(`input[name="verbosity_quick"][value="${currentVerbosity}"]`);
        if (quickRadio) quickRadio.checked = true;
    }

    _pushLiveSettings() {
        // Debounced: send updated settings to backend during active session.
        // voice-config PUT now signals the agent via room metadata automatically.
        if (this._pushLiveSettingsTimer) clearTimeout(this._pushLiveSettingsTimer);
        this._pushLiveSettingsTimer = setTimeout(async () => {
            if (!this.sessionId) return;
            try {
                const settings = this.getVoiceSettings();
                await fetch(`/api/session/${this.sessionId}/voice-config`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settings),
                });
                LOG.info('Live settings pushed:', settings);
                this._persistSettings();
            } catch (e) {
                LOG.warn('Failed to push live settings:', e);
            }
        }, 500);
    }

    async _loadAvailableProviders() {
        try {
            const resp = await fetch('/api/llm/providers');
            if (!resp.ok) return;
            const data = await resp.json();
            const providers = data.providers || [];
            for (const p of providers) {
                const radios = document.querySelectorAll(`input[name="llm_provider"][value="${p.id}"]`);
                radios.forEach(radio => {
                    if (!p.available) {
                        radio.disabled = true;
                        radio.closest('.segment')?.classList.add('disabled');
                    }
                });
            }
            // If current selection is disabled, fall back to default
            const checked = document.querySelector('input[name="llm_provider"]:checked');
            if (checked && checked.disabled) {
                const defaultProvider = data.default || 'deepseek';
                const fallback = document.querySelector(`input[name="llm_provider"][value="${defaultProvider}"]`);
                if (fallback && !fallback.disabled) {
                    fallback.checked = true;
                } else {
                    // Pick first available
                    const first = document.querySelector('input[name="llm_provider"]:not(:disabled)');
                    if (first) first.checked = true;
                }
                this._persistSettings();
            }
        } catch {}
    }

    // ===== Screen Management =====

    showScreen(screenName) {
        this._currentScreenName = screenName;
        Object.values(this.screens).forEach(s => s.classList.remove('active'));
        if (this.screens[screenName]) {
            this.screens[screenName].classList.add('active');
        }
        if (screenName === 'landing') {
            this._initLandingAnimations();
        }
        this._updateHeaderContext(screenName);
    }

    _updateHeaderContext(screenName) {
        const navAbout = document.getElementById('nav-about');
        const navSessions = document.getElementById('nav-sessions');

        // Visibility rules per screen:
        // Landing:   hide "О платформе" (we ARE on it), show "Мои сессии" (if returning)
        // Dashboard: show "О платформе", hide "Мои сессии" (we ARE on it)
        // Session:   show "О платформе", show "Мои сессии"
        // Review:    show "О платформе", show "Мои сессии"
        const hasVisited = !!localStorage.getItem('hasVisited');

        if (navAbout) navAbout.style.display = screenName === 'landing' ? 'none' : '';
        if (navSessions) navSessions.style.display =
            (screenName === 'dashboard' || !hasVisited) ? 'none' : '';

        // Active indicator
        document.querySelectorAll('.header-nav-item').forEach(el => el.classList.remove('active'));
        if (screenName === 'landing' && navAbout) navAbout.classList.add('active');
        if (screenName === 'dashboard' && navSessions) navSessions.classList.add('active');
    }

    _initLandingAnimations() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });

        document.querySelectorAll('.landing-animate').forEach(el => observer.observe(el));
    }

    // ===== DASHBOARD =====

    async showDashboard() {
        this.stopAnketaPolling();

        // First-time visitors see the landing page instead of the dashboard
        if (!localStorage.getItem('hasVisited')) {
            this.showScreen('landing');
            this._initLandingAnimations();
            return;
        }

        this.showScreen('dashboard');
        this._updateSettingsLockState();
        await this.loadSessions(this.currentFilter);
    }

    async loadSessions(statusFilter = '') {
        this._currentStatusFilter = statusFilter;
        try {
            const url = statusFilter
                ? `/api/sessions?status=${statusFilter}`
                : '/api/sessions';
            const resp = await fetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            this.renderSessionsTable(data.sessions);
            // Update filter counts when loading all sessions
            if (!statusFilter) {
                this._updateFilterCounts(data.sessions || []);
            }
        } catch (error) {
            LOG.error('Failed to load sessions:', error);
            showToast('Ошибка загрузки сессий', 'error');
        }
    }

    _updateFilterCounts(sessions) {
        const counts = { '': sessions.length };
        sessions.forEach(s => {
            counts[s.status] = (counts[s.status] || 0) + 1;
        });
        document.querySelectorAll('.filter-tab').forEach(tab => {
            const status = tab.dataset.status;
            const count = counts[status] || 0;
            const existing = tab.querySelector('.filter-count');
            if (existing) existing.remove();
            if (count > 0) {
                const badge = document.createElement('span');
                badge.className = 'filter-count';
                badge.textContent = count;
                tab.appendChild(badge);
            }
        });
    }

    renderSessionsTable(sessions) {
        const tbody = document.getElementById('sessions-tbody');
        const empty = document.getElementById('dashboard-empty');
        const table = document.getElementById('sessions-table');
        const selectAll = document.getElementById('select-all-sessions');
        const deleteBtn = document.getElementById('delete-selected-btn');

        if (!sessions || sessions.length === 0) {
            tbody.innerHTML = '';
            table.style.display = 'none';
            empty.style.display = 'flex';
            if (deleteBtn) deleteBtn.style.display = 'none';
            if (selectAll) selectAll.checked = false;
            return;
        }

        table.style.display = '';
        empty.style.display = 'none';

        const statusLabels = {
            active: 'активна',
            paused: 'на паузе',
            confirmed: 'подтверждена',
            declined: 'отклонена',
            reviewing: 'AI обрабатывает',
        };

        const LIVEKIT_CLOUD_BASE = 'https://cloud.livekit.io';

        tbody.innerHTML = sessions.map(s => {
            const date = this._formatDate(s.created_at);
            const company = s.company_name || '—';
            const contact = s.contact_name || '—';
            const status = statusLabels[s.status] || s.status;
            const duration = s.duration_seconds > 0
                ? `${Math.round(s.duration_seconds / 60)} мин`
                : '—';
            const isActive = s.status === 'active' || s.status === 'paused';
            const shortId = s.session_id.substring(0, 8);
            const roomName = s.room_name || '—';

            return `<tr data-link="${s.unique_link}" data-status="${s.status}" data-session-id="${s.session_id}">
                <td class="td-checkbox"><input type="checkbox" class="session-checkbox" data-id="${s.session_id}"></td>
                <td class="td-id" title="${s.session_id}">${shortId}</td>
                <td class="td-date">${date}</td>
                <td class="td-company">${this._escapeHtml(company)}</td>
                <td class="td-contact">${this._escapeHtml(contact)}</td>
                <td class="td-docs">${s.has_documents ? '<span class="doc-indicator" title="Есть документы">📎</span>' : ''}</td>
                <td class="td-room">${roomName !== '—' ? `<a href="${LIVEKIT_CLOUD_BASE}" target="_blank" class="room-link" title="${roomName}">${roomName}</a>` : '—'}</td>
                <td><span class="status-badge status-${s.status}">${status}</span></td>
                <td class="td-duration">${duration}</td>
                <td class="td-actions">
                    ${isActive
                        ? `<button class="btn-table btn-table-primary" data-action="open" data-link="${s.unique_link}">Открыть</button>`
                        : `<button class="btn-table" data-action="review" data-link="${s.unique_link}">Просмотр</button>`
                    }
                    <button class="btn-table btn-table-muted" data-action="copy" data-link="${s.unique_link}" title="Копировать ссылку">🔗</button>
                </td>
            </tr>`;
        }).join('');

        // Checkbox handlers
        this._setupCheckboxHandlers();

        // Click handlers for table buttons
        tbody.querySelectorAll('button[data-action]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                const link = btn.dataset.link;
                if (action === 'open') {
                    this.router.navigate(`/session/${link}`);
                } else if (action === 'review') {
                    this.router.navigate(`/session/${link}/review`);
                } else if (action === 'copy') {
                    this.copyToClipboard(`${window.location.origin}/session/${link}`);
                    showToast('Ссылка скопирована');
                }
            });
        });

        // Click on row to navigate (but not on checkbox or link)
        tbody.querySelectorAll('tr[data-link]').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.closest('.session-checkbox') || e.target.closest('.td-checkbox') || e.target.closest('a') || e.target.closest('button')) return;
                const link = row.dataset.link;
                const status = row.dataset.status;
                if (status === 'active' || status === 'paused') {
                    this.router.navigate(`/session/${link}`);
                } else {
                    this.router.navigate(`/session/${link}/review`);
                }
            });
        });
    }

    _setupCheckboxHandlers() {
        const selectAll = document.getElementById('select-all-sessions');
        const deleteBtn = document.getElementById('delete-selected-btn');

        const updateDeleteBtn = () => {
            const checked = document.querySelectorAll('.session-checkbox:checked');
            if (deleteBtn) {
                deleteBtn.style.display = checked.length > 0 ? '' : 'none';
                deleteBtn.textContent = `Удалить выбранные (${checked.length})`;
            }
            if (selectAll) {
                const all = document.querySelectorAll('.session-checkbox');
                selectAll.checked = all.length > 0 && checked.length === all.length;
                selectAll.indeterminate = checked.length > 0 && checked.length < all.length;
            }
        };

        // Select all toggle
        if (selectAll) {
            selectAll.addEventListener('change', () => {
                document.querySelectorAll('.session-checkbox').forEach(cb => {
                    cb.checked = selectAll.checked;
                });
                updateDeleteBtn();
            });
        }

        // Individual checkbox change
        document.querySelectorAll('.session-checkbox').forEach(cb => {
            cb.addEventListener('change', updateDeleteBtn);
            cb.addEventListener('click', (e) => e.stopPropagation());
        });

        // Delete button
        if (deleteBtn) {
            deleteBtn.onclick = () => this.deleteSelectedSessions();
        }
    }

    async deleteSelectedSessions() {
        const checked = document.querySelectorAll('.session-checkbox:checked');
        const ids = Array.from(checked).map(cb => cb.dataset.id);
        if (ids.length === 0) return;

        const confirmed = await this._showConfirmModal(
            `Удалить ${ids.length} ${ids.length === 1 ? 'сессию' : 'сессий'}? Это действие необратимо.`
        );
        if (!confirmed) return;

        try {
            // Stop polling if we're deleting the current session
            if (this.sessionId && ids.includes(this.sessionId)) {
                this.stopAnketaPolling();
                this.sessionId = null;
            }

            const resp = await fetch('/api/sessions/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_ids: ids }),
            });
            const data = await resp.json();
            showToast(`Удалено ${data.deleted} сессий`);
            this.loadSessions(this._currentStatusFilter);
        } catch (error) {
            LOG.error('Delete sessions failed:', error);
            showToast('Ошибка при удалении', 'error');
        }
    }

    // ===== SESSION (Interview) =====

    async showSession(link) {
        // If already in this session, just show the screen + push any setting changes
        if (this.uniqueLink === link && this.sessionId) {
            this.showScreen('session');
            document.getElementById('session-screen').classList.add('voice-active');
            this._syncQuickSettings();
            this.startAnketaPolling();
            // Send updated voice settings (user may have changed editable ones on Dashboard).
            // voice-config PUT now signals the agent via room metadata automatically —
            // no need to call /reconnect (which could recreate room + dispatch a 2nd agent).
            try {
                await fetch(`/api/session/${this.sessionId}/voice-config`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.getVoiceSettings()),
                });
                LOG.info('Voice config synced on session return');
            } catch (e) {
                LOG.warn('Failed to sync voice config on return:', e);
            }
            return;
        }

        this.showScreen('session');
        document.getElementById('session-screen').classList.add('voice-active');
        await this.resumeOrStartSession(link);
    }

    async resumeOrStartSession(link) {
        // Abort any in-flight session load to prevent race conditions
        if (this._sessionAbortController) {
            this._sessionAbortController.abort();
        }
        this._sessionAbortController = new AbortController();
        const signal = this._sessionAbortController.signal;

        try {
            let sessionData = null;

            // Try to find session by link
            let response = await fetch(`/api/session/by-link/${link}`, { signal });
            if (response.ok) {
                sessionData = await response.json();
            } else {
                response = await fetch(`/api/session/${link}`, { signal });
                if (response.ok) {
                    sessionData = await response.json();
                }
            }

            if (!sessionData) {
                showToast('Сессия не найдена', 'error');
                this.router.navigate('/');
                return;
            }

            this.sessionId = sessionData.session_id || link;
            this.uniqueLink = sessionData.unique_link || link;
            this.roomName = sessionData.room_name || null;

            // Sync settings lock state when resuming session
            this._updateSettingsLockState();

            // Update header
            this.elements.sessionCompany.textContent = sessionData.company_name || 'Новая сессия';
            this.updateAnketaStatus(sessionData.status || 'active');

            if (sessionData.status === 'active' || sessionData.status === 'paused') {
                this.elements.pauseBtn.disabled = false;
            }

            // Detect consultation type from voice_config or anketa_data
            if (sessionData.voice_config && sessionData.voice_config.consultation_type) {
                this.consultationType = sessionData.voice_config.consultation_type;
            } else if (sessionData.anketa_data && sessionData.anketa_data.anketa_type === 'interview') {
                this.consultationType = 'interview';
            } else {
                this.consultationType = 'consultation';
            }

            // Save original config for locked settings guard
            if (sessionData.voice_config) {
                this._sessionOriginalConfig = { ...sessionData.voice_config };
            } else {
                this._sessionOriginalConfig = { ...this.getVoiceSettings() };
            }

            // ✅ FIX БАГ #6: Reset state, but preserve isPaused if session is paused
            this.isPaused = (sessionData.status === 'paused');
            this.localEdits = {};
            this.focusedField = null;

            // Restore paused UI state if session is paused
            if (sessionData.status === 'paused') {
                this.elements.pauseBtn.classList.add('paused');
                this.elements.pauseBtn.querySelector('.icon').textContent = '▶';
                this.elements.micBtn.disabled = true;
                document.getElementById('pause-overlay')?.classList.add('visible');
            } else {
                this.elements.pauseBtn.classList.remove('paused');
                this.elements.pauseBtn.querySelector('.icon').textContent = '⏸';
                this.elements.micBtn.disabled = false;
                document.getElementById('pause-overlay')?.classList.remove('visible');
            }

            // Restore dialogue
            this.elements.dialogueContainer.innerHTML = '';
            this.messageCount = 0;
            if (sessionData.dialogue_history && Array.isArray(sessionData.dialogue_history)) {
                sessionData.dialogue_history.forEach(msg => {
                    const role = msg.role === 'assistant' ? 'ai' : 'user';
                    this.addMessage(role, msg.content);
                });
            }

            // Restore anketa (or clear if empty)
            if (sessionData.anketa_data) {
                this.populateAnketaForm(sessionData.anketa_data);
                // Restore stepper progress immediately
                const normalized = this._normalizeAnketaData(sessionData.anketa_data);
                this._updateStepperProgress(normalized);
                // Calculate and show initial progress
                const anketaFieldSet = new Set(this.anketaFields);
                const filledKeys = Object.keys(normalized).filter(
                    k => anketaFieldSet.has(k) && normalized[k] && normalized[k] !== '' &&
                    !(Array.isArray(normalized[k]) && normalized[k].length === 0)
                );
                const pct = this.anketaFields.length > 0
                    ? Math.min(100, Math.round(filledKeys.length / this.anketaFields.length * 100))
                    : 0;
                this.updateProgress(pct);
                this._lastFieldCount = filledKeys.length;
                this._lastPct = pct;
            } else {
                this.clearAnketaForm();
                // v4.3: Don't reset progress to 0 — wait for first poll to set real value
                // this.updateProgress(0);
            }
            this.lastServerAnketa = sessionData.anketa_data ? { ...sessionData.anketa_data } : {};

            this.startAnketaPolling();
            this._syncQuickSettings();

            // ✅ FIX БАГ #3: Reconnect to LiveKit if active, paused, OR processing
            if (sessionData.status === 'active' || sessionData.status === 'paused' || sessionData.status === 'processing') {
                try {
                    // ✅ UX #1: Show feedback during reconnect (0-1000ms window)
                    this.elements.voiceStatus.textContent = 'Подключаемся к серверу...';
                    this.updateConnectionStatus(false);
                    showToast('Восстанавливаем соединение...', 'info');

                    // Send current slider values so the agent uses updated voice_config
                    await fetch(`/api/session/${this.sessionId}/voice-config`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this.getVoiceSettings()),
                    });

                    const reconResp = await fetch(`/api/session/${this.sessionId}/reconnect`);
                    if (reconResp.ok) {
                        const reconData = await reconResp.json();
                        await this.connectToRoom(reconData.livekit_url, reconData.user_token, reconData.room_name);
                        this.updateConnectionStatus(true);
                        // ✅ FIX БАГ #4: REMOVED setTimeout — startRecording will be triggered by RoomEvent.Connected
                        // Store session status for RoomEvent.Connected handler
                        this._resumedSessionStatus = sessionData.status;

                        // ✅ UX: Update voice status after reconnect
                        if (sessionData.status === 'paused') {
                            this.elements.voiceStatus.textContent = 'На паузе';
                            document.querySelector('.wave')?.classList.add('inactive');
                        } else {
                            this.elements.voiceStatus.textContent = 'Подключено. Ожидание...';
                        }
                    }
                } catch (err) {
                    LOG.error('Reconnect error:', err);
                    this.updateConnectionStatus(false);
                }
            } else {
                // ✅ UX #2: Hide connection status ONLY for truly finished sessions
                // For other statuses (processing, reviewing), show connection status
                if (sessionData.status === 'confirmed' || sessionData.status === 'declined') {
                    const status = this.elements.connectionStatus;
                    if (status) status.style.display = 'none';
                } else {
                    // Show connection status for all other statuses
                    const status = this.elements.connectionStatus;
                    if (status) status.style.display = 'flex';
                    this.updateConnectionStatus(false);
                }
            }

        } catch (error) {
            if (error.name === 'AbortError') return; // navigation cancelled
            LOG.error('Error loading session:', error);
            showToast('Ошибка загрузки сессии', 'error');
        }
    }

    async createAndGoToSession() {
        if (this._isCreatingSession) return;
        this._isCreatingSession = true;
        LOG.info('=== CREATE SESSION ===');
        // Stop any existing polling to prevent dual-polling
        this.stopAnketaPolling();

        this.elements.newSessionBtn.disabled = true;
        this.elements.newSessionBtn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px"></span>Создание...';

        try {
            // Check agent health
            try {
                const healthResp = await fetch('/api/agent/health');
                const health = await healthResp.json();
                if (!health.worker_alive) {
                    throw new Error('Голосовой агент не запущен. Запустите: ./scripts/agent.sh start');
                }
            } catch (e) {
                if (e.message.includes('агент')) throw e;
            }

            // Create session
            const response = await fetch('/api/session/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pattern: 'interaction',
                    voice_settings: this.getVoiceSettings(),
                }),
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.sessionId = data.session_id;
            this.uniqueLink = data.unique_link;
            this.roomName = data.room_name;

            // Sync settings lock state when creating new session
            this._updateSettingsLockState();

            // Reset state
            this.elements.dialogueContainer.innerHTML = '';
            this.messageCount = 0;
            this.localEdits = {};
            this.lastServerAnketa = {};
            this.focusedField = null;
            this._lastFieldCount = 0;
            this._lastPct = 0;
            this._agentSpoke = false;
            this.consultationType = this.getVoiceSettings().consultation_type || 'consultation';
            this._sessionOriginalConfig = { ...this.getVoiceSettings() };
            this.clearAnketaForm();

            // Update UI
            this.elements.sessionCompany.textContent = 'Новая сессия';
            this.updateAnketaStatus('active');
            this.elements.pauseBtn.disabled = false;

            // Update URL without triggering router.resolve() → showSession().
            // showSession's quick-path calls /reconnect which can dispatch a 2nd agent
            // due to LiveKit Cloud eventual consistency (list_rooms misses just-created room).
            window.history.pushState({}, '', `/session/${data.unique_link}`);

            const sessionScreen = document.getElementById('session-screen');
            if (!sessionScreen.classList.contains('active')) {
                this.showScreen('session');
            }
            sessionScreen.classList.add('voice-active');

            // Connect to LiveKit
            this.updateConnectionStatus('connecting');
            await this.connectToRoom(data.livekit_url, data.user_token, data.room_name);
            this.updateConnectionStatus(true);
            this.startAnketaPolling();
            this._syncQuickSettings();

            // Agent sends its own greeting via voice (appears via TranscriptionReceived).
            // No hardcoded greeting — avoids duplicate messages in chat.

            // ✅ FIX БАГ #4: REMOVED setTimeout — startRecording will be triggered by RoomEvent.Connected

        } catch (error) {
            LOG.error('Session create failed:', error);
            showToast(error.message || 'Ошибка создания сессии', 'error', 5000);
        } finally {
            this._isCreatingSession = false;
            this.elements.newSessionBtn.disabled = false;
            this.elements.newSessionBtn.textContent = '+ Новая сессия';
        }
    }

    goBackToDashboard() {
        this.stopAnketaPolling();
        // Disconnect voice to avoid orphaned audio tracks
        if (this.isRecording) {
            this.stopRecording();
        }
        if (this.room) {
            this.room.disconnect();
            this.room = null;
        }
        this.isConnected = false;
        this.localParticipant = null;
        document.getElementById('session-screen')?.classList.remove('voice-active');
        this.router.navigate('/');
    }

    // ===== SESSION CONTROL HANDLERS (Level 1 - Global) =====

    handleAllSessions() {
        if (this.isRecording) {
            const confirmMsg = 'Сессия активна. Остановить и вернуться к списку?';
            if (!confirm(confirmMsg)) return;
            this.handleStopSession();
        }
        this.router.navigate('/');
    }

    async handleStopSession() {
        if (!this.isRecording && !this.isConnected) return;

        const confirmMsg = 'Остановить текущую сессию?';
        if (!confirm(confirmMsg)) return;

        // Stop recording and disconnect
        await this.stopRecording();
        if (this.room) {
            await this.room.disconnect();
        }

        // Update session status to 'paused' on backend using existing endpoint
        if (this.sessionId) {
            try {
                await fetch(`/api/session/${this.sessionId}/end`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
            } catch (err) {
                console.error('Failed to end session:', err);
            }
        }

        // Update UI
        document.getElementById('btn-stop-session')?.setAttribute('disabled', 'true');
        document.getElementById('btn-start-session')?.removeAttribute('disabled');

        showToast('Сессия приостановлена', 'info', 2000);
    }

    async handleStartSession() {
        if (!this.sessionId) {
            showToast('Нет активной сессии для возобновления', 'error', 2000);
            return;
        }

        try {
            // Fetch fresh token from reconnect endpoint
            const resp = await fetch(`/api/session/${this.sessionId}/reconnect`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!resp.ok) {
                const errData = await resp.json();
                throw new Error(errData.detail || 'Reconnect failed');
            }

            const data = await resp.json();

            // Reconnect to LiveKit room with fresh token
            await this.connectToRoom(data.livekit_url, data.token, data.room_name);

            // Update UI
            document.getElementById('btn-stop-session')?.removeAttribute('disabled');
            document.getElementById('btn-start-session')?.setAttribute('disabled', 'true');

            showToast('Сессия возобновлена', 'success', 2000);
        } catch (err) {
            console.error('Failed to restart session:', err);
            showToast(`Ошибка возобновления: ${err.message}`, 'error', 3000);
        }
    }

    async handleRecordSession() {
        if (!this.sessionId) {
            showToast('Нет активной сессии для экспорта', 'error', 2000);
            return;
        }

        try {
            // Use existing export endpoint with json format
            const resp = await fetch(`/api/session/${this.sessionId}/export/json`);
            if (!resp.ok) throw new Error('Export failed');

            const blob = await resp.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `session-${this.sessionId}-${Date.now()}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            showToast('Сессия сохранена', 'success', 2000);
        } catch (err) {
            console.error('Failed to export session:', err);
            showToast('Ошибка при сохранении сессии', 'error', 2000);
        }
    }

    handleGoToResults() {
        if (!this.sessionId) {
            showToast('Нет активной сессии', 'error', 2000);
            return;
        }

        // Navigate to review screen
        if (this.uniqueLink) {
            this.router.navigate(`/review/${this.uniqueLink}`);
        } else {
            showToast('Ссылка на результаты недоступна', 'error', 2000);
        }
    }

    async handleSaveAnketa() {
        if (!this.sessionId) {
            showToast('Нет активной сессии', 'error', 2000);
            return;
        }

        // Guard: prevent saving if not in edit mode
        if (!this.isAnketaEditable) {
            console.warn('Anketa is read-only, save aborted');
            return;
        }

        try {
            // Reuse existing saveAnketa logic
            await this.saveAnketa();
            showToast('Анкета сохранена', 'success', 2000);
        } catch (err) {
            console.error('Failed to save anketa:', err);
            showToast(`Ошибка сохранения: ${err.message}`, 'error', 3000);
        }
    }

    // ===== SESSION REVIEW =====

    async showSessionReview(link) {
        this.showScreen('review');
        this._reviewLink = link;

        try {
            const resp = await fetch(`/api/session/by-link/${link}`);
            if (!resp.ok) throw new Error('Сессия не найдена');
            const data = await resp.json();

            // Store session ID for export functionality
            if (data.session_id) {
                this.sessionId = data.session_id;
            }

            // Header
            document.getElementById('review-company').textContent = data.company_name || '—';
            const badge = document.getElementById('review-status-badge');
            const statusLabels = { active: 'активна', paused: 'на паузе', confirmed: 'подтверждена', declined: 'отклонена' };
            badge.textContent = statusLabels[data.status] || data.status;
            badge.className = `anketa-status-badge status-${data.status}`;

            const dur = document.getElementById('review-duration');
            dur.textContent = data.duration_seconds > 0
                ? `${Math.round(data.duration_seconds / 60)} мин`
                : '';

            // Show/hide resume button
            const resumeBtn = this.elements.reviewResumeBtn;
            resumeBtn.style.display = (data.status === 'active' || data.status === 'paused') ? '' : 'none';

            // Render anketa read-only
            this._renderReviewAnketa(data.anketa_data || {});

            // Render dialogue
            this._renderReviewDialogue(data.dialogue_history || []);

        } catch (error) {
            LOG.error('Error loading review:', error);
            showToast('Ошибка загрузки сессии', 'error');
        }
    }

    _renderReviewAnketa(anketa) {
        const container = document.getElementById('review-anketa-content');

        // v5.0: Interview mode review rendering
        if (anketa.anketa_type === 'interview') {
            this._renderReviewAnketaInterview(anketa, container);
            return;
        }

        const normalized = this._normalizeAnketaData(anketa);

        const sections = [
            { title: 'Контакты', fields: ['company_name', 'contact_name', 'contact_role', 'phone', 'email', 'website'] },
            { title: 'О бизнесе', fields: ['industry', 'specialization', 'business_type', 'company_description', 'services', 'client_types', 'current_problems', 'business_goals'] },
            { title: 'Голосовой агент', fields: ['agent_name', 'agent_purpose', 'agent_tasks', 'integrations', 'voice_gender', 'voice_tone', 'call_direction', 'transfer_conditions'] },
            { title: 'Дополнительно', fields: ['constraints', 'compliance_requirements', 'call_volume', 'budget', 'timeline', 'additional_notes'] },
        ];

        const fieldLabels = {
            company_name: 'Компания', contact_name: 'Контакт', contact_role: 'Должность',
            phone: 'Телефон', email: 'Email', website: 'Сайт',
            industry: 'Отрасль', specialization: 'Специализация', business_type: 'Тип бизнеса',
            company_description: 'Описание', services: 'Услуги', client_types: 'Типы клиентов',
            current_problems: 'Проблемы', business_goals: 'Цели',
            agent_name: 'Имя агента', agent_purpose: 'Назначение', agent_tasks: 'Задачи',
            integrations: 'Интеграции', voice_gender: 'Голос', voice_tone: 'Тон',
            call_direction: 'Направление', transfer_conditions: 'Перевод на оператора',
            constraints: 'Ограничения', compliance_requirements: 'Требования регулятора',
            call_volume: 'Объём', budget: 'Бюджет', timeline: 'Сроки', additional_notes: 'Примечания',
        };

        let html = '';
        for (const section of sections) {
            const filledFields = section.fields.filter(f => {
                const v = normalized[f];
                return v && (Array.isArray(v) ? v.length > 0 : String(v).trim() !== '');
            });
            if (filledFields.length === 0) continue;

            html += `<div class="review-section"><div class="review-section-title">${section.title}</div>`;
            for (const f of filledFields) {
                const value = normalized[f];
                const display = Array.isArray(value) ? value.join(', ') : String(value);
                html += `<div class="review-field">
                    <span class="review-label">${fieldLabels[f] || f}</span>
                    <span class="review-value">${this._escapeHtml(display)}</span>
                </div>`;
            }
            html += '</div>';
        }

        container.innerHTML = html || '<p class="review-empty">Анкета пуста</p>';
    }

    _renderReviewAnketaInterview(anketa, container) {
        let html = '';

        // Section 1: Respondent info
        const infoFields = [
            { key: 'contact_name', label: 'Имя' },
            { key: 'contact_role', label: 'Роль' },
            { key: 'interview_title', label: 'Тема интервью' },
        ];
        const filledInfo = infoFields.filter(f => anketa[f.key] && String(anketa[f.key]).trim());
        if (filledInfo.length > 0) {
            html += '<div class="review-section"><div class="review-section-title">Респондент</div>';
            for (const f of filledInfo) {
                html += `<div class="review-field">
                    <span class="review-label">${f.label}</span>
                    <span class="review-value">${this._escapeHtml(String(anketa[f.key]))}</span>
                </div>`;
            }
            html += '</div>';
        }

        // Section 2: Q&A Pairs
        const qaPairs = anketa.qa_pairs || [];
        if (qaPairs.length > 0) {
            html += '<div class="review-section"><div class="review-section-title">Вопросы и ответы</div>';
            for (const qa of qaPairs) {
                const topic = qa.topic && qa.topic !== 'general' ? ` <span class="qa-topic">${this._escapeHtml(qa.topic)}</span>` : '';
                html += `<div class="qa-pair">
                    <div class="qa-question">В: ${this._escapeHtml(qa.question || '')}${topic}</div>
                    <div class="qa-answer">${this._escapeHtml(qa.answer || '\u2014')}</div>
                </div>`;
            }
            html += '</div>';
        }

        // Section 3: Detected topics
        const topics = anketa.detected_topics || [];
        if (topics.length > 0) {
            html += '<div class="review-section"><div class="review-section-title">Выявленные темы</div>';
            html += `<div class="topics-list">${topics.map(t => `<span class="topic-tag">${this._escapeHtml(t)}</span>`).join(' ')}</div>`;
            html += '</div>';
        }

        // Section 4: Key quotes
        const quotes = anketa.key_quotes || [];
        if (quotes.length > 0) {
            html += '<div class="review-section"><div class="review-section-title">Ключевые цитаты</div>';
            for (const q of quotes) {
                html += `<blockquote class="key-quote">"${this._escapeHtml(q)}"</blockquote>`;
            }
            html += '</div>';
        }

        // Section 5: AI Summary & Insights
        if (anketa.summary || (anketa.key_insights && anketa.key_insights.length > 0)) {
            html += '<div class="review-section"><div class="review-section-title">AI-анализ</div>';
            if (anketa.summary) {
                html += `<p class="interview-summary">${this._escapeHtml(anketa.summary)}</p>`;
            }
            if (anketa.key_insights && anketa.key_insights.length > 0) {
                html += '<div class="insights-list">';
                for (const insight of anketa.key_insights) {
                    html += `<div class="insight-item">${this._escapeHtml(insight)}</div>`;
                }
                html += '</div>';
            }
            html += '</div>';
        }

        container.innerHTML = html || '<p class="review-empty">Анкета интервью пуста</p>';
    }

    _renderReviewDialogue(history) {
        const container = document.getElementById('review-dialogue');
        if (!history.length) {
            container.innerHTML = '<p class="review-empty">Нет сообщений</p>';
            return;
        }

        container.innerHTML = history.map(msg => {
            const role = msg.role === 'assistant' ? 'ai' : 'user';
            const label = role === 'ai' ? 'Агент' : 'Клиент';
            return `<div class="review-msg review-msg-${role}">
                <span class="review-msg-author">${label}</span>
                <span class="review-msg-text">${this._escapeHtml(msg.content)}</span>
            </div>`;
        }).join('');
    }

    // ===== LiveKit Connection =====

    async connectToRoom(url, token, roomName) {
        LOG.info('connectToRoom:', { url, roomName, tokenLength: token ? token.length : 0 });

        // Show loading spinner
        const loadingOverlay = document.createElement('div');
        loadingOverlay.className = 'loading-overlay visible';
        loadingOverlay.id = 'loading-overlay';
        loadingOverlay.innerHTML = '<div class="spinner"></div><div class="loading-text">Подключение...</div>';
        this.elements.dialogueContainer.appendChild(loadingOverlay);

        const { Room, RoomEvent, Track } = LivekitClient;

        // Disconnect previous room to avoid orphaned connections
        if (this.room) {
            try { await this.room.disconnect(); } catch {}
        }

        this.room = new Room({ adaptiveStream: true, dynacast: true });

        this.room.on(RoomEvent.Connected, () => {
            LOG.event('Connected', { roomName: this.room.name });
            this.isConnected = true;
            this.updateStatusTicker('Консультация началась');

            // ✅ SPRINT 3: Проактивное уведомление об автозаполнении анкеты
            if (!this.isPaused && this.consultationType === 'consultation') {
                setTimeout(() => {
                    showToast(
                        '💡 Агент автоматически заполняет анкету во время разговора',
                        'info',
                        6000
                    );
                    this.updateStatusTicker('🎯 Анкета заполняется автоматически');
                }, 2000);
            }

            // ✅ FIX БАГ #4: Auto-start recording when room is fully connected (resume scenario)
            // Only start if NOT paused and NOT already recording
            if (!this.isPaused && !this.isRecording && this.sessionId) {
                // Small delay to ensure localParticipant is fully initialized
                setTimeout(() => {
                    if (!this.isPaused && !this.isRecording) {
                        this.startRecording();
                    }
                }, 500);
            }
        });

        this.room.on(RoomEvent.Disconnected, (reason) => {
            LOG.event('Disconnected', { reason });
            this.isConnected = false;
            this.updateConnectionStatus(false);
            // Stop recording and clean up on disconnect
            if (this.isRecording) {
                this.stopRecording();
            }
            this.stopAnketaPolling();
            // Clean up orphaned audio elements
            this.agentAudioElements.forEach(({ track, element }) => {
                try { track.detach(); } catch {}
                if (element.parentNode) element.remove();
            });
            this.agentAudioElements.clear();

            // Show reconnect prompt if we're still on the session screen
            if (this._currentScreenName === 'session' && this.sessionId) {
                showToast('Соединение потеряно. Вернитесь к сессии для переподключения.', 'error', 6000);
            }
        });

        this.room.on(RoomEvent.Reconnecting, () => LOG.event('Reconnecting'));
        this.room.on(RoomEvent.Reconnected, () => {
            LOG.event('Reconnected');
            this.isConnected = true;
            this.updateConnectionStatus(true);
            // Restore recording if not paused
            if (!this.isPaused && !this.isRecording) {
                this.startRecording();
            }
            this.startAnketaPolling();
        });

        this.room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
            LOG.event('TrackSubscribed', { trackKind: track.kind, participant: participant.identity });
            if (track.kind === Track.Kind.Audio) {
                const existing = this.agentAudioElements.get(track.sid);
                if (existing) {
                    existing.track.detach();
                    if (existing.element.parentNode) existing.element.remove();
                    this.agentAudioElements.delete(track.sid);
                }

                const audioElement = track.attach();
                audioElement.muted = false;
                audioElement.volume = 1.0;
                document.body.appendChild(audioElement);
                this.agentAudioElements.set(track.sid, { track, element: audioElement });

                const playPromise = audioElement.play();
                if (playPromise) {
                    playPromise.catch(() => {
                        const resumeAudio = () => {
                            audioElement.muted = false;
                            audioElement.play().catch(() => {});
                            document.removeEventListener('click', resumeAudio);
                        };
                        document.addEventListener('click', resumeAudio);
                    });
                }
            }
        });

        this.room.on(RoomEvent.TrackUnsubscribed, (track) => {
            if (track.kind === Track.Kind.Audio) {
                const entry = this.agentAudioElements.get(track.sid);
                if (entry) {
                    track.detach();
                    if (entry.element.parentNode) entry.element.remove();
                    this.agentAudioElements.delete(track.sid);
                }
            }
        });

        this.room.on(RoomEvent.DataReceived, (payload, participant) => {
            try {
                const data = JSON.parse(new TextDecoder().decode(payload));
                this.handleAgentMessage(data);
            } catch (e) {
                LOG.warn('Failed to parse data message:', e);
            }
        });

        // LiveKit Agents SDK forwards transcriptions automatically via Transcription API
        const transcriptionEvent = RoomEvent.TranscriptionReceived || 'transcriptionReceived';
        this.room.on(transcriptionEvent, (segments, participant) => {
            if (!segments || segments.length === 0) return;

            for (const segment of segments) {
                if (!segment.final) continue;
                const text = segment.text?.trim();
                if (!text) continue;

                const isUser = participant?.identity === this.room.localParticipant?.identity;
                this.addMessage(isUser ? 'user' : 'ai', text);
                if (!isUser && !this._agentSpoke) {
                    this._agentSpoke = true;
                    this.updateStatusTicker('Агент слушает вас');
                }
            }
        });

        await this.room.connect(url, token);
        // Remove loading spinner
        document.getElementById('loading-overlay')?.remove();
        this.localParticipant = this.room.localParticipant;
        LOG.info('Connected to room:', this.room.name);
    }

    // ===== Session Pause / Resume =====

    togglePause() {
        if (this.isPaused) {
            this.resumeSession();
        } else {
            this.pauseSession();
        }
    }

    async pauseSession() {
        LOG.info('=== PAUSE SESSION ===');
        this.isPaused = true;

        // Stop mic but keep room connected
        await this.stopRecording();

        // UI: pause button → resume button
        this.elements.pauseBtn.classList.add('paused');
        this.elements.pauseBtn.querySelector('.icon').textContent = '▶';
        this.elements.micBtn.disabled = true;
        this.elements.micBtn.classList.remove('inactive');
        this.elements.micBtn.classList.add('paused');
        document.getElementById('pause-overlay')?.classList.add('visible');
        this.elements.voiceStatus.textContent = 'На паузе';
        document.querySelector('.wave')?.classList.add('inactive');
    }

    async resumeSession() {
        LOG.info('=== RESUME SESSION ===');
        this.isPaused = false;

        // UI: resume button → pause button
        this.elements.pauseBtn.classList.remove('paused');
        this.elements.pauseBtn.querySelector('.icon').textContent = '⏸';
        this.elements.micBtn.disabled = false;
        this.elements.micBtn.classList.remove('paused');
        document.getElementById('pause-overlay')?.classList.remove('visible');

        // Send updated voice settings so agent picks up mid-session changes.
        // voice-config PUT signals the agent via room metadata automatically.
        if (this.sessionId) {
            try {
                await fetch(`/api/session/${this.sessionId}/voice-config`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.getVoiceSettings()),
                });
                LOG.info('Voice config updated on resume');
            } catch (e) {
                LOG.warn('Failed to update voice config on resume:', e);
            }
        }

        // Restart recording
        await this.startRecording();
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
        if (this.isRecording) return;

        // ✅ FIX БАГ #5: Guard check for localParticipant
        if (!this.localParticipant) {
            LOG.error('Cannot start recording: localParticipant is null');
            showToast('Ошибка подключения к комнате. Попробуйте через несколько секунд.', 'error');
            return;
        }

        LOG.info('=== START RECORDING ===');
        try {
            const { createLocalAudioTrack } = LivekitClient;
            this.audioTrack = await createLocalAudioTrack({
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            });

            await this.localParticipant.publishTrack(this.audioTrack);

            if (this.audioTrack.isMuted) {
                await this.audioTrack.unmute();
            }

            this.isRecording = true;
            this.elements.micBtn.classList.remove('inactive', 'paused');
            this.elements.micBtn.classList.add('recording');
            this.elements.micBtn.title = 'Остановить запись (идет запись)';  // v4.3: tooltip
            this.elements.voiceStatus.textContent = 'Слушаю...';
            document.querySelector('.wave')?.classList.remove('inactive');

            this.startAudioLevelMonitor();

        } catch (error) {
            LOG.error('Mic start failed:', error);
            this.isRecording = false;
            this.elements.micBtn.classList.remove('recording');
            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                showToast('Микрофон заблокирован. Нажмите на иконку замка в адресной строке, разрешите микрофон и обновите страницу.', 'error', 8000);
            } else {
                showToast('Не удалось получить доступ к микрофону', 'error');
            }
        }
    }

    async stopRecording() {
        LOG.info('=== STOP RECORDING ===');

        if (this.audioLevelInterval) {
            clearInterval(this.audioLevelInterval);
            this.audioLevelInterval = null;
        }

        if (this._monitorAudioContext) {
            try { this._monitorAudioContext.close(); } catch {}
            this._monitorAudioContext = null;
        }

        if (this.audioTrack) {
            try {
                if (this.localParticipant) {
                    await this.localParticipant.unpublishTrack(this.audioTrack);
                }
            } catch (e) {
                LOG.warn('unpublishTrack error (room may be disconnected):', e);
            }
            this.audioTrack.stop();
            this.audioTrack = null;
        }

        this.isRecording = false;
        this.elements.micBtn.classList.remove('recording');
        this.elements.micBtn.classList.add('inactive');
        this.elements.micBtn.title = 'Начать запись';  // v4.3: tooltip
        this.elements.voiceStatus.textContent = 'Микрофон выключен';
        document.querySelector('.wave')?.classList.add('inactive');
    }

    startAudioLevelMonitor() {
        if (!this.audioTrack || !this.audioTrack.mediaStreamTrack) return;

        const mediaStreamTrack = this.audioTrack.mediaStreamTrack;
        const stream = new MediaStream([mediaStreamTrack]);
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);

        // Store reference for cleanup
        this._monitorAudioContext = audioContext;

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        let sampleCount = 0;

        this.audioLevelInterval = setInterval(() => {
            analyser.getByteFrequencyData(dataArray);
            sampleCount++;
            if (sampleCount % 40 === 0) {
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                const avg = sum / dataArray.length;
                if (avg < 5) LOG.warn('Very low audio level — check microphone');
            }
        }, 100);
    }

    // ===== Message Handling =====

    handleAgentMessage(data) {
        switch (data.type) {
            case 'message': this.addMessage('ai', data.content); break;
            case 'transcript': this.addMessage('user', data.content); break;
            case 'phase': break;
            case 'progress': this.updateProgress(data.percentage); break;
            case 'complete': break;
            default: LOG.warn('Unknown message type:', data.type);
        }
    }

    addMessage(author, content) {
        const placeholder = document.getElementById('dialogue-placeholder');
        if (placeholder) placeholder.remove();

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${author}`;

        const authorSpan = document.createElement('div');
        authorSpan.className = 'author';
        const authorLabels = { ai: 'AI-Консультант', user: 'Вы', system: 'Система' };
        authorSpan.textContent = authorLabels[author] || author;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        contentDiv.textContent = content;

        const timeEl = document.createElement('time');
        timeEl.className = 'message-time';
        timeEl.textContent = this._formatTime(new Date());

        messageDiv.appendChild(authorSpan);
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timeEl);

        this.elements.dialogueContainer.appendChild(messageDiv);
        this.elements.dialogueContainer.scrollTop = this.elements.dialogueContainer.scrollHeight;

        this.messageCount++;
        this._lastMessageTimestamp = Date.now();
    }

    // ===== Anketa Polling =====

    startAnketaPolling() {
        this.stopAnketaPolling();
        this._anketaFirstPollDone = false;
        this._lastMessageTimestamp = Date.now();
        // Show skeleton loading on empty fields
        this.elements.anketaForm?.querySelectorAll('input, textarea').forEach(el => {
            if (!el.value) el.classList.add('field-loading');
        });
        this._scheduleNextPoll();
        this.pollAnketa();
    }

    stopAnketaPolling() {
        if (this._pollTimeoutId) {
            clearTimeout(this._pollTimeoutId);
            this._pollTimeoutId = null;
        }
        if (this.anketaPollingInterval) {
            clearInterval(this.anketaPollingInterval);
            this.anketaPollingInterval = null;
        }
    }

    _getPollingInterval() {
        // Adaptive: 2s active, 5s idle (>30s no message), 10s tab hidden
        if (document.hidden) return 10000;
        const idle = Date.now() - (this._lastMessageTimestamp || Date.now());
        if (idle > 30000) return 5000;
        return 2000;
    }

    _scheduleNextPoll() {
        if (this._pollTimeoutId) clearTimeout(this._pollTimeoutId);
        this._pollTimeoutId = setTimeout(async () => {
            await this.pollAnketa();
            if (this.sessionId) this._scheduleNextPoll();
        }, this._getPollingInterval());
    }

    async pollAnketa() {
        if (!this.sessionId) return;

        try {
            const response = await fetch(`/api/session/${this.sessionId}/anketa`);
            if (!response.ok) {
                if (response.status === 404) {
                    LOG.warn(`[POLLING] Session ${this.sessionId} not found, stopping polling`);
                    this.stopAnketaPolling();
                }
                // Don't increment failure count for non-200 responses (could be intentional 404)
                return;
            }

            const data = await response.json();

            // SUCCESS: Reset failure count
            this._pollingFailureCount = 0;

            // SPRINT 5: Debug logging
            const completion = data.completion_rate || 0;
            const messageCount = this.messageHistory?.length || 0;
            const filledFields = data.anketa_data ? Object.keys(data.anketa_data).filter(
                k => data.anketa_data[k] && data.anketa_data[k] !== '' &&
                !(Array.isArray(data.anketa_data[k]) && data.anketa_data[k].length === 0)
            ).length : 0;

            // Debug logging (console only, no visual noise)
            if (window.location.search.includes('debug=true')) {
                console.log('[POLLING] Anketa update', {
                    session_id: this.sessionId,
                    completion_rate: completion,
                    message_count: messageCount,
                    fields_filled: filledFields,
                    total_fields: this.anketaFields.length,
                    status: data.status
                });
            }

            // SPRINT 5: Update debug panel
            this._updateDebugPanel(completion, filledFields, this.anketaFields.length, messageCount, true);

            if (data.status) {
                this.updateAnketaStatus(data.status);
                if (data.status === 'reviewing') {
                    this.updateStatusTicker('AI анализирует ответы...', true);
                } else if (data.status === 'confirmed') {
                    this.updateStatusTicker('Консультация завершена');
                }
            }

            // Update company name in header
            if (data.company_name) {
                this.elements.sessionCompany.textContent = data.company_name;
            }

            // Remove skeleton on first successful poll
            if (!this._anketaFirstPollDone) {
                this._anketaFirstPollDone = true;
                this.elements.anketaForm?.querySelectorAll('.field-loading').forEach(el => {
                    el.classList.remove('field-loading');
                });
            }

            if (data.anketa_data) {
                // v5.0: Detect anketa type for rendering
                if (data.anketa_data.anketa_type === 'interview') {
                    this.consultationType = 'interview';
                }

                // Normalize field names (business_description→company_description, etc.)
                // BEFORE counting, so mapped fields are included in progress
                const normalized = this._normalizeAnketaData(data.anketa_data);
                const anketaFieldSet = new Set(this.anketaFields);
                const keys = Object.keys(normalized).filter(
                    k => anketaFieldSet.has(k) &&
                    normalized[k] && normalized[k] !== '' &&
                    !(Array.isArray(normalized[k]) && normalized[k].length === 0)
                );
                if (this.consultationType === 'interview') {
                    this.updateAnketaFromServerInterview(data.anketa_data);
                } else {
                    this.updateAnketaFromServer(data.anketa_data);
                    this.updateAIBlocksSummary(data.anketa_data);
                }
                this.lastServerAnketa = { ...data.anketa_data };

                let pct;
                if (this.consultationType === 'interview') {
                    const qaPairs = data.anketa_data.qa_pairs || [];
                    const answered = qaPairs.filter(qa => qa.answer && qa.answer.trim()).length;
                    pct = qaPairs.length > 0 ? Math.min(100, Math.round(answered / qaPairs.length * 100)) : 0;
                } else {
                    pct = this.anketaFields.length > 0
                        ? Math.min(100, Math.round(keys.length / this.anketaFields.length * 100))
                        : 0;
                }
                this.updateProgress(pct);
                this._updateStepperProgress(normalized);

                // SPRINT 3: Update header anketa status
                const headerStatus = document.getElementById('header-anketa-status');
                const headerProgress = document.getElementById('header-anketa-progress');

                if (this.consultationType === 'consultation' && !this.isPaused && this.isConnected) {
                    if (pct > 0 && pct < 100 && headerStatus) {
                        headerStatus.style.display = 'flex';
                        if (headerProgress) {
                            headerProgress.textContent = `${Math.round(pct)}%`;
                        }
                    }

                    // Hide when complete
                    if (pct >= 100 && headerStatus) {
                        setTimeout(() => {
                            headerStatus.style.display = 'none';
                        }, 5000);
                    }
                }

                // Status ticker + toast notifications
                const prevCount = this._lastFieldCount || 0;
                if (prevCount === 0 && keys.length > 0) {
                    showToast('Анкета заполняется автоматически по ходу беседы', 'info', 4000);
                    this.updateStatusTicker('Анкета заполняется автоматически');
                } else if (keys.length > prevCount && prevCount > 0) {
                    const diff = keys.length - prevCount;
                    showToast(`Анкета обновлена — +${diff} ${diff === 1 ? 'поле' : 'полей'}`, 'success', 4000);  // SPRINT 4: было 'info', 2500ms
                    this.updateStatusTicker(`Заполнено ${keys.length} из ${this.anketaFields.length} полей`, true);  // pulse = true
                }
                if (pct >= 50 && (this._lastPct || 0) < 50) {
                    this.updateStatusTicker('Собрано больше половины данных');
                }
                this._lastFieldCount = keys.length;
                this._lastPct = pct;
            }
        } catch (error) {
            // SPRINT 5: Not silent anymore - log errors with failure count
            LOG.error('[POLLING] Anketa fetch failed:', error);

            // Show toast only after multiple consecutive failures
            this._pollingFailureCount = (this._pollingFailureCount || 0) + 1;
            if (this._pollingFailureCount >= 3) {
                showToast('Проблема с обновлением анкеты. Попробуйте обновить страницу.', 'warning', 5000);
            }
        }
    }

    // ===== Anketa Normalization =====

    _normalizeAnketaData(data) {
        const normalized = { ...data };

        if (data.business_description && !data.company_description) {
            normalized.company_description = data.business_description;
        }
        if (data.contact_phone && !data.phone) {
            normalized.phone = data.contact_phone;
        }
        if (data.contact_email && !data.email) {
            normalized.email = data.contact_email;
        }
        if (data.agent_functions && Array.isArray(data.agent_functions) && !data.agent_tasks) {
            normalized.agent_tasks = data.agent_functions.map(f => {
                if (typeof f === 'object' && f !== null) {
                    return f.name + (f.description ? ': ' + f.description : '');
                }
                return String(f);
            });
        }
        if (data.integrations && Array.isArray(data.integrations) && data.integrations.length > 0) {
            if (typeof data.integrations[0] === 'object' && data.integrations[0] !== null) {
                normalized.integrations = data.integrations.map(i => {
                    if (typeof i === 'object') return i.name + (i.purpose ? ' — ' + i.purpose : '');
                    return String(i);
                });
            }
        }

        return normalized;
    }

    // ===== Document Upload =====

    async uploadDocuments(fileList) {
        if (!this.sessionId) return;

        const statusEl = this.elements.docUploadStatus;
        const btn = this.elements.docUploadBtn;

        btn.disabled = true;
        btn.textContent = 'Загрузка...';
        if (statusEl) statusEl.textContent = '';

        const formData = new FormData();
        for (const file of fileList) formData.append('files', file);

        try {
            const response = await fetch(
                `/api/session/${this.sessionId}/documents/upload`,
                { method: 'POST', body: formData }
            );

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(err.detail || `Upload failed: ${response.status}`);
            }

            const data = await response.json();
            const names = data.documents.join(', ');
            if (statusEl) {
                statusEl.innerHTML =
                    `<span class="upload-success">Загружено: ${names}</span>` +
                    `<span class="upload-summary">⏳ AI обрабатывает документ...</span>` +
                    (data.summary ? `<span class="upload-summary">${data.summary}</span>` : '');
            }

            this.addMessage('system', `Документ загружен: ${names}. Анализирую...`);

        } catch (error) {
            LOG.error('Document upload failed:', error);
            if (statusEl) statusEl.innerHTML = `<span class="upload-error">${error.message}</span>`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Прикрепить документ';
            this.elements.docUploadInput.value = '';
        }
    }

    // ===== AI Blocks Summary =====

    updateAIBlocksSummary(data) {
        let hasAny = false;
        let html = '';
        for (const block of this.aiBlocks) {
            const items = data[block.key];
            const count = Array.isArray(items) ? items.length : 0;
            if (count > 0) hasAny = true;
            const cls = count > 0 ? 'ai-block-filled' : 'ai-block-empty';
            html += `<div class="ai-block-item ${cls}">
                <span class="ai-block-label">${block.label}</span>
                <span class="ai-block-count">${count}</span>
            </div>`;
        }

        const section = document.getElementById('ai-blocks-section');
        const summary = document.getElementById('ai-blocks-summary');
        if (section && summary) {
            section.style.display = hasAny ? 'block' : 'none';
            summary.innerHTML = html;
        }
    }

    // ===== Interview Anketa Rendering =====

    updateAnketaFromServerInterview(anketaData) {
        // For interview mode, we render Q&A pairs instead of form fields
        const container = this.elements.anketaForm;
        if (!container) return;

        // Clear form and render interview data
        container.innerHTML = '';

        // Section 1: Respondent info
        const infoSection = document.createElement('div');
        infoSection.className = 'anketa-section';
        infoSection.innerHTML = `
            <div class="anketa-section-title">Респондент</div>
            <div class="anketa-field">
                <label>Имя</label>
                <input type="text" value="${this._escapeHtml(anketaData.contact_name || '')}" readonly>
            </div>
            <div class="anketa-field">
                <label>Роль</label>
                <input type="text" value="${this._escapeHtml(anketaData.contact_role || '')}" readonly>
            </div>
            <div class="anketa-field">
                <label>Тема интервью</label>
                <input type="text" value="${this._escapeHtml(anketaData.interview_title || '')}" readonly>
            </div>
        `;
        container.appendChild(infoSection);

        // Section 2: Q&A Pairs
        const qaPairs = anketaData.qa_pairs || [];
        if (qaPairs.length > 0) {
            const qaSection = document.createElement('div');
            qaSection.className = 'anketa-section';
            let qaHtml = '<div class="anketa-section-title">Вопросы и ответы</div>';
            for (const qa of qaPairs) {
                const topic = qa.topic && qa.topic !== 'general' ? `<span class="qa-topic">${this._escapeHtml(qa.topic)}</span>` : '';
                qaHtml += `
                    <div class="qa-pair">
                        <div class="qa-question">В: ${this._escapeHtml(qa.question || '')} ${topic}</div>
                        <div class="qa-answer">${this._escapeHtml(qa.answer || '\u2014')}</div>
                    </div>
                `;
            }
            qaSection.innerHTML = qaHtml;
            container.appendChild(qaSection);
        }

        // Section 3: Detected topics
        const topics = anketaData.detected_topics || [];
        if (topics.length > 0) {
            const topicSection = document.createElement('div');
            topicSection.className = 'anketa-section';
            topicSection.innerHTML = `
                <div class="anketa-section-title">Выявленные темы</div>
                <div class="topics-list">${topics.map(t => `<span class="topic-tag">${this._escapeHtml(t)}</span>`).join(' ')}</div>
            `;
            container.appendChild(topicSection);
        }

        // Section 4: Key quotes
        const quotes = anketaData.key_quotes || [];
        if (quotes.length > 0) {
            const quotesSection = document.createElement('div');
            quotesSection.className = 'anketa-section';
            let quotesHtml = '<div class="anketa-section-title">Ключевые цитаты</div>';
            for (const q of quotes) {
                quotesHtml += `<blockquote class="key-quote">"${this._escapeHtml(q)}"</blockquote>`;
            }
            quotesSection.innerHTML = quotesHtml;
            container.appendChild(quotesSection);
        }

        // Section 5: AI Summary & Insights
        if (anketaData.summary || (anketaData.key_insights && anketaData.key_insights.length > 0)) {
            const aiSection = document.createElement('div');
            aiSection.className = 'anketa-section';
            let aiHtml = '<div class="anketa-section-title">AI-анализ</div>';
            if (anketaData.summary) {
                aiHtml += `<p class="interview-summary">${this._escapeHtml(anketaData.summary)}</p>`;
            }
            if (anketaData.key_insights && anketaData.key_insights.length > 0) {
                aiHtml += '<div class="insights-list">';
                for (const insight of anketaData.key_insights) {
                    aiHtml += `<div class="insight-item">${this._escapeHtml(insight)}</div>`;
                }
                aiHtml += '</div>';
            }
            aiSection.innerHTML = aiHtml;
            container.appendChild(aiSection);
        }
    }

    // ===== Anketa Form =====

    setupAnketaFieldListeners() {
        const formFields = this.elements.anketaForm?.querySelectorAll('input, textarea');
        if (!formFields) return;

        formFields.forEach(field => {
            const fieldName = field.dataset.field;
            field.addEventListener('focus', () => { this.focusedField = fieldName; });
            field.addEventListener('blur', () => {
                if (this.focusedField === fieldName) this.focusedField = null;
            });
            field.addEventListener('input', () => {
                this.localEdits[fieldName] = true;
                this.scheduleAnketaSave();
                // Auto-resize textareas on user input
                if (field.tagName === 'TEXTAREA') {
                    field.style.height = 'auto';
                    field.style.height = field.scrollHeight + 'px';
                }
            });
        });

        // v5.4: User scroll guard — suppress auto-scroll when user scrolls manually
        const anketaForm = document.getElementById('anketa-form');
        if (anketaForm) {
            anketaForm.addEventListener('scroll', () => {
                this._userScrolling = true;
                clearTimeout(this._userScrollTimer);
                this._userScrollTimer = setTimeout(() => { this._userScrolling = false; }, 15000);
            }, { passive: true });
        }

        // Stepper click-to-scroll (with locked step feedback)
        document.querySelectorAll('.stepper-step[data-section]').forEach(step => {
            step.addEventListener('click', () => {
                if (step.classList.contains('locked')) {
                    showToast('Заполните предыдущие разделы для разблокировки', 'info', 2500);
                    return;
                }
                const idx = step.dataset.section;
                const section = document.querySelector(`.anketa-section[data-section-index="${idx}"]`);
                if (section && anketaForm) {
                    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    this._userScrolling = true;
                    clearTimeout(this._userScrollTimer);
                    this._userScrollTimer = setTimeout(() => { this._userScrolling = false; }, 15000);
                }
            });
        });
    }

    updateAnketaFromServer(anketaData) {
        const normalized = this._normalizeAnketaData(anketaData);
        let firstUpdatedField = null;
        let updatedCount = 0;

        this.anketaFields.forEach(fieldName => {
            if (this.focusedField === fieldName) return;
            if (this.localEdits[fieldName]) return;

            const element = document.getElementById(`anketa-${fieldName}`);
            if (!element) return;

            const serverValue = normalized[fieldName];
            let displayValue = '';

            if (serverValue !== null && serverValue !== undefined) {
                if (this.arrayFields.has(fieldName) && Array.isArray(serverValue)) {
                    displayValue = serverValue.join('\n');
                } else {
                    displayValue = String(serverValue);
                }
            }

            if (element.value !== displayValue) {
                // v5.4: Detect first-time fill for auto-scroll
                const wasPreviouslyEmpty = !this._previousFieldValues[fieldName];
                const isNowFilled = displayValue !== '';

                element.value = displayValue;
                element.classList.add('field-updated');
                setTimeout(() => element.classList.remove('field-updated'), 3000);

                updatedCount++;

                // Track first newly-filled field element for auto-scroll (to field, not section)
                if (wasPreviouslyEmpty && isNowFilled && !firstUpdatedField) {
                    firstUpdatedField = element;
                }
            }

            // Track field values for next comparison
            this._previousFieldValues[fieldName] = displayValue;
        });

        // Auto-scroll to the first newly-filled field (not just section)
        if (firstUpdatedField && !this._userScrolling) {
            this._scrollToField(firstUpdatedField);
        }

        // Auto-resize textareas that received new content
        if (updatedCount > 0) {
            this.elements.anketaForm?.querySelectorAll('textarea').forEach(ta => {
                if (ta.value) {
                    ta.style.height = 'auto';
                    ta.style.height = ta.scrollHeight + 'px';
                }
            });
        }
    }

    populateAnketaForm(anketaData) {
        const normalized = this._normalizeAnketaData(anketaData);

        this.anketaFields.forEach(fieldName => {
            const element = document.getElementById(`anketa-${fieldName}`);
            if (!element) return;

            const value = normalized[fieldName];
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
            const el = document.getElementById(`anketa-${fieldName}`);
            if (el) el.value = '';
        });
        this.updateAnketaStatus('');
    }

    scheduleAnketaSave() {
        if (this.anketaSaveTimeout) clearTimeout(this.anketaSaveTimeout);
        this.anketaSaveTimeout = setTimeout(() => this.saveAnketa(), 1000);
    }

    async saveAnketa() {
        if (!this.sessionId) return;

        // In interview mode, the form is replaced with read-only Q&A rendering —
        // DOM fields are absent. Use cached server data to avoid sending empty PUT.
        if (this.consultationType === 'interview') {
            if (this.lastServerAnketa && Object.keys(this.lastServerAnketa).length > 0) {
                // Nothing to save from DOM; server already has the data
            }
            return;
        }

        const anketaData = {};
        this.anketaFields.forEach(fieldName => {
            const el = document.getElementById(`anketa-${fieldName}`);
            if (!el) return;
            const rawValue = el.value.trim();
            if (this.arrayFields.has(fieldName)) {
                anketaData[fieldName] = rawValue
                    ? rawValue.split('\n').map(s => s.trim()).filter(s => s.length > 0)
                    : [];
            } else {
                anketaData[fieldName] = rawValue || '';
            }
        });

        // Guard: do not send completely empty data (all fields blank)
        const hasAnyValue = Object.values(anketaData).some(v =>
            Array.isArray(v) ? v.length > 0 : v !== ''
        );
        if (!hasAnyValue) return;

        try {
            const response = await fetch(`/api/session/${this.sessionId}/anketa`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ anketa_data: anketaData }),
            });
            if (response.ok) {
                // Only clear localEdits for fields whose values match what we just saved.
                // Fields edited by the user AFTER the save started should remain protected.
                const safeEdits = {};
                for (const [field, flag] of Object.entries(this.localEdits)) {
                    const el = document.getElementById(`anketa-${field}`);
                    if (el && el.value.trim() !== (anketaData[field] || '').toString()) {
                        safeEdits[field] = true; // user changed this field since save started
                    }
                }
                this.localEdits = safeEdits;
                this.lastServerAnketa = { ...anketaData };
            }
        } catch (error) {
            LOG.error('Error saving anketa:', error);
        }
    }

    // ===== Anketa Actions =====

    async confirmAnketa() {
        if (!this.sessionId || this._confirmingAnketa) return;
        this._confirmingAnketa = true;

        if (this.anketaSaveTimeout) clearTimeout(this.anketaSaveTimeout);
        await this.saveAnketa();

        try {
            const response = await fetch(`/api/session/${this.sessionId}/confirm`, { method: 'POST' });
            if (response.ok) {
                this.updateAnketaStatus('confirmed');
                this.elements.confirmAnketaBtn.disabled = true;
                this.elements.confirmAnketaBtn.textContent = 'Подтверждено';
                showToast('Анкета подтверждена');
                // Disconnect voice and navigate to review screen
                this.stopAnketaPolling();
                await this.stopRecording();
                if (this.room) {
                    await this.room.disconnect();
                    this.room = null;
                }
                document.getElementById('session-screen')?.classList.remove('voice-active');
                this.router.navigate(`/session/${this.uniqueLink}/review`);
            } else {
                showToast('Ошибка подтверждения', 'error');
            }
        } catch (error) {
            LOG.error('Error confirming:', error);
            showToast('Ошибка подтверждения', 'error');
        } finally {
            this._confirmingAnketa = false;
        }
    }

    async saveAndLeave() {
        if (!this.sessionId || this._savingAndLeaving) return;
        const confirmed = await this._showConfirmModal('Сохранить и выйти? Голосовое соединение будет прервано, но данные сохранятся.');
        if (!confirmed) return;
        this._savingAndLeaving = true;

        if (this.anketaSaveTimeout) clearTimeout(this.anketaSaveTimeout);
        await this.saveAnketa();

        try {
            await fetch(`/api/session/${this.sessionId}/end`, { method: 'POST' });

            this.stopAnketaPolling();
            await this.stopRecording();

            this.agentAudioElements.forEach(({ track, element }) => {
                try { track.detach(); } catch {}
                if (element.parentNode) element.remove();
            });
            this.agentAudioElements.clear();

            if (this.room) {
                await this.room.disconnect();
                this.room = null;
            }

            const link = `${window.location.origin}/session/${this.uniqueLink}`;
            this.copyToClipboard(link);

            showToast('Сессия сохранена. Ссылка скопирована.');
            this.updateAnketaStatus('paused');
            this.updateConnectionStatus(false);
            this.elements.pauseBtn.disabled = true;
            this.isPaused = false;

            // Reset session identity so showSession() will reconnect
            this.sessionId = null;
            this.uniqueLink = null;
            this.localParticipant = null;
            this._sessionOriginalConfig = null;
            document.getElementById('session-screen')?.classList.remove('voice-active');

            this.router.navigate('/');

        } catch (error) {
            LOG.error('Error saving:', error);
            showToast('Ошибка сохранения', 'error');
        } finally {
            this._savingAndLeaving = false;
        }
    }

    async copySessionLink() {
        if (!this.uniqueLink) {
            showToast('Ссылка ещё не доступна');
            return;
        }
        const link = `${window.location.origin}/session/${this.uniqueLink}`;
        await this.copyToClipboard(link);
        showToast('Ссылка скопирована');
    }

    goToDashboard() {
        localStorage.setItem('hasVisited', '1');
        this.showScreen('dashboard');
        this.loadSessions();
    }

    async exportAnketa(format) {
        if (!this.sessionId) {
            showToast('Нет активной сессии');
            return;
        }

        try {
            if (format === 'pdf') {
                // Open styled HTML in new tab for print-to-PDF
                window.open(`/api/session/${this.sessionId}/export/pdf`, '_blank');
            } else if (format === 'md') {
                // Download markdown file
                const response = await fetch(`/api/session/${this.sessionId}/export/md`);
                if (!response.ok) throw new Error('Export failed');
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = response.headers.get('Content-Disposition')?.split('filename="')[1]?.replace('"', '') || 'anketa.md';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('Markdown скачан');
            }
        } catch (error) {
            console.error('Export error:', error);
            showToast('Ошибка экспорта', 'error');
        }
    }

    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try { document.execCommand('copy'); return true; }
            catch { return false; }
            finally { document.body.removeChild(textarea); }
        }
    }

    // ===== UI Helpers =====

    updateAnketaStatus(status) {
        const badge = this.elements.anketaStatusBadge;
        if (!badge) return;

        badge.className = 'anketa-status-badge';
        const labels = {
            active: 'активна', paused: 'на паузе', reviewing: 'AI обрабатывает',
            confirmed: 'подтверждена', declined: 'отклонена',
        };
        badge.textContent = labels[status] || 'ожидание';
        if (status) badge.classList.add(`status-${status}`);
    }

    updateConnectionStatus(state) {
        const status = this.elements.connectionStatus;
        if (!status) return;
        status.classList.remove('connected', 'connecting');
        if (state === true) {
            status.classList.add('connected');
            status.querySelector('.text').textContent = 'Подключен';
        } else if (state === 'connecting') {
            status.classList.add('connecting');
            status.querySelector('.text').textContent = 'Подключаемся...';
        } else {
            status.querySelector('.text').textContent = 'Не подключен';
        }
    }

    updateProgress(percentage) {
        const clamped = Math.min(100, Math.max(0, percentage));
        if (this.elements.progressFill) {
            this.elements.progressFill.style.width = `${clamped}%`;

            // SPRINT 4: Анимация при обновлении
            this.elements.progressFill.classList.add('updated');
            setTimeout(() => {
                this.elements.progressFill.classList.remove('updated');
            }, 500);
        }
        if (this.elements.progressText) {
            this.elements.progressText.textContent = `${Math.round(clamped)}% заполнено`;
        }
    }

    // Scroll anketa form to a section by index (debounced)
    _scrollToSection(sectionIndex) {
        if (this._scrollDebounceTimer) return;
        this._scrollDebounceTimer = setTimeout(() => { this._scrollDebounceTimer = null; }, 600);

        const section = document.querySelector(`.anketa-section[data-section-index="${sectionIndex}"]`);
        if (!section) return;

        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // Scroll anketa form to a specific field element (debounced)
    _scrollToField(fieldElement) {
        if (this._scrollDebounceTimer) return;
        this._scrollDebounceTimer = setTimeout(() => { this._scrollDebounceTimer = null; }, 600);

        if (!fieldElement) return;
        const wrapper = fieldElement.closest('.anketa-field') || fieldElement;
        wrapper.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    // v5.4: Update stepper pipeline progress per section
    _updateStepperProgress(normalized) {
        if (this.consultationType === 'interview') return; // stepper is for consultation mode only

        const steps = document.querySelectorAll('.stepper-step[data-section]');
        const connectors = document.querySelectorAll('.stepper-connector');
        let lastFilledSection = -1;

        this.sectionDefs.forEach((sec, i) => {
            const filled = sec.fields.filter(f => {
                const v = normalized[f];
                return v && v !== '' && !(Array.isArray(v) && v.length === 0);
            }).length;
            const total = sec.fields.length;
            const pct = Math.round(filled / total * 100);
            const step = steps[i];
            if (!step) return;

            // Remove all state classes
            step.classList.remove('active', 'partial', 'complete');

            if (pct === 100) {
                step.classList.add('complete');
                lastFilledSection = i;
            } else if (pct > 0) {
                step.classList.add('partial');
                lastFilledSection = i;
            }

            // Update connector fill (connector[i] connects step[i] to step[i+1])
            if (i < connectors.length) {
                const connector = connectors[i];
                const fill = connector.querySelector('.stepper-connector-fill');
                if (fill) {
                    fill.style.width = `${pct}%`;
                }
                connector.classList.toggle('complete', pct === 100);
            }
        });

        // Mark the last section with new data as "active"
        if (lastFilledSection >= 0) {
            const activeStep = steps[lastFilledSection];
            if (activeStep && !activeStep.classList.contains('complete')) {
                activeStep.classList.add('active');
            } else if (activeStep && activeStep.classList.contains('complete')) {
                // If last filled is complete, mark next incomplete as active
                for (let j = lastFilledSection + 1; j < this.sectionDefs.length; j++) {
                    if (steps[j] && !steps[j].classList.contains('complete')) {
                        steps[j].classList.add('active');
                        break;
                    }
                }
            }
        }

        // Section 5 (AI): check if ai-blocks-section is visible
        const aiStep = steps[4];
        const aiSection = document.getElementById('ai-blocks-section');
        if (aiStep && aiSection && aiSection.style.display !== 'none') {
            aiStep.classList.remove('locked');
            aiStep.classList.add('complete');
        }
    }

    updateStatusTicker(text, pulsing = false) {
        const ticker = document.getElementById('status-ticker-text');
        const dot = document.querySelector('.status-ticker-dot');
        if (ticker) ticker.textContent = text;
        if (dot) dot.classList.toggle('pulse', pulsing);
    }

    _formatDate(isoString) {
        if (!isoString) return '—';
        const d = new Date(isoString);
        const now = new Date();
        const day = String(d.getDate()).padStart(2, '0');
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const hours = String(d.getHours()).padStart(2, '0');
        const mins = String(d.getMinutes()).padStart(2, '0');

        if (d.toDateString() === now.toDateString()) {
            return `Сегодня ${hours}:${mins}`;
        }

        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (d.toDateString() === yesterday.toDateString()) {
            return `Вчера ${hours}:${mins}`;
        }

        return `${day}.${month} ${hours}:${mins}`;
    }

    _formatTime(date) {
        const h = String(date.getHours()).padStart(2, '0');
        const m = String(date.getMinutes()).padStart(2, '0');
        return `${h}:${m}`;
    }

    _showConfirmModal(text) {
        return new Promise((resolve) => {
            const modal = document.getElementById('confirm-modal');
            const textEl = document.getElementById('confirm-modal-text');
            const yesBtn = document.getElementById('confirm-modal-yes');
            const noBtn = document.getElementById('confirm-modal-no');
            if (!modal) { resolve(confirm(text)); return; }

            textEl.textContent = text;
            modal.style.display = '';

            const cleanup = (result) => {
                modal.style.display = 'none';
                yesBtn.removeEventListener('click', onYes);
                noBtn.removeEventListener('click', onNo);
                resolve(result);
            };

            const onYes = () => cleanup(true);
            const onNo = () => cleanup(false);

            yesBtn.addEventListener('click', onYes);
            noBtn.addEventListener('click', onNo);
        });
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}


// Init
document.addEventListener('DOMContentLoaded', () => {
    LOG.info('DOM loaded, creating app...');
    window.app = new VoiceInterviewerApp();
});
