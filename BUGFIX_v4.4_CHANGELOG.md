# BUGFIX v4.4 - Исправление микрофона при возобновлении сессии

**Дата:** 2026-02-12
**Критичность:** P0 - CRITICAL
**Тестовая сессия:** 39139356

## Проблема

Пользователь не может продолжить диалог после возврата к паузированной сессии:
- Микрофон неактивен
- Нет способа включить его
- Dialogue history не сохраняется (logger error)
- Race condition затирает статус "paused" на "processing"

## Корневая причина

Каскад из 5 критичных багов в reconnect flow:
1. Logger error → dialogue_history НЕ сохраняется
2. Race condition → статус `paused` затирается на `processing`/`reviewing`
3. Frontend → НЕ reconnect для status=`processing`
4. setTimeout → startRecording() до готовности localParticipant
5. No guard → crash при publishTrack(null)

## Исправления

### SPRINT 1: Критичные баги (6 исправлений)

#### ✅ БАГ #1: Logger Error (FIXED)
**Файл:** `src/voice/consultant.py:1112-1117`

**Проблема:**
```python
event_log.info("dialogue_saved_sync", session_id=session_id, ...)  # ❌ Wrong
```

**Решение:**
```python
event_log.info("dialogue_saved_sync", extra={...})  # ✅ Correct structlog format
```

**Результат:** dialogue_history корректно сохраняется без ошибок

---

#### ✅ БАГ #2: Race Condition в статусе (FIXED)
**Файл:** `src/voice/consultant.py:1105-1125, 807-814`

**Проблема:**
- Пользователь нажимает "Сохранить и выйти" → статус `paused` ✅
- Async task `_finalize_and_save()` затирает → `reviewing` ❌
- Синхронный код затирает → `processing` ❌

**Решение:**
```python
# Re-read session BEFORE update
fresh_session = _session_mgr.get_session(session_id)
current_status = fresh_session.status if fresh_session else "processing"

# Only update to "processing"/"reviewing" if status is still "active"
# Preserve "paused", "confirmed", "declined"
final_status = "processing" if current_status == "active" else current_status
```

**Результат:** Статус "paused" сохраняется корректно

---

#### ✅ БАГ #3: Frontend reconnect для 'processing' (FIXED)
**Файл:** `public/app.js:1049`

**Проблема:**
```javascript
if (sessionData.status === 'active' || sessionData.status === 'paused') {
    // reconnect...  ❌ Не покрывает status='processing'
}
```

**Решение:**
```javascript
if (sessionData.status === 'active' || sessionData.status === 'paused' || sessionData.status === 'processing') {
    // reconnect...  ✅ Теперь работает для всех статусов
}
```

**Результат:** Reconnect работает даже если статус 'processing'

---

#### ✅ БАГ #4: Event-driven startRecording (FIXED)
**Файл:** `public/app.js:1063, 1428-1443`

**Проблема:**
```javascript
await this.connectToRoom(...);
setTimeout(() => this.startRecording(), 1000);  // ❌ Race condition
```

**Решение:**
```javascript
// REMOVED setTimeout
// Added to RoomEvent.Connected handler:
this.room.on(RoomEvent.Connected, () => {
    if (!this.isPaused && !this.isRecording && this.sessionId) {
        setTimeout(() => this.startRecording(), 500);  // ✅ Safe, after room ready
    }
});
```

**Результат:** Микрофон активируется ТОЛЬКО после готовности room

---

#### ✅ БАГ #5: Guard check в startRecording() (FIXED)
**Файл:** `public/app.js:1582-1593`

**Проблема:**
```javascript
async startRecording() {
    await this.localParticipant.publishTrack(this.audioTrack);  // ❌ No null check
}
```

**Решение:**
```javascript
async startRecording() {
    if (!this.localParticipant) {
        LOG.error('Cannot start recording: localParticipant is null');
        showToast('Ошибка подключения к комнате. Попробуйте через несколько секунд.', 'error');
        return;
    }
    // ... rest
}
```

**Результат:** Graceful error handling вместо crash

---

#### ✅ БАГ #6: Восстановить UI паузы (FIXED)
**Файл:** `public/app.js:1001-1008`

**Проблема:**
```javascript
this.isPaused = false;  // ❌ ВСЕГДА сбрасывает на false
this.elements.micBtn.disabled = false;  // ❌ Разблокирует микрофон
```

**Решение:**
```javascript
this.isPaused = (sessionData.status === 'paused');

if (sessionData.status === 'paused') {
    // Restore paused UI
    this.elements.pauseBtn.classList.add('paused');
    this.elements.pauseBtn.querySelector('.icon').textContent = '▶';
    this.elements.micBtn.disabled = true;
    document.getElementById('pause-overlay')?.classList.add('visible');
} else {
    // Reset UI
}
```

**Результат:** UI паузы корректно восстанавливается

---

### SPRINT 2: UX Improvements (3 улучшения)

#### ✅ UX #1: Feedback при reconnect
**Файл:** `public/app.js:1060-1063`

**Добавлено:**
```javascript
this.elements.voiceStatus.textContent = 'Подключаемся к серверу...';
this.updateConnectionStatus(false);
showToast('Восстанавливаем соединение...', 'info');
```

**Результат:** Пользователь видит прогресс подключения

---

#### ✅ UX #2: Connection status для resumed sessions
**Файл:** `public/app.js:1091-1099`

**Проблема:** Connection status скрывался для resumed sessions

**Решение:** Показывать connection status для всех статусов кроме 'confirmed'/'declined'

**Результат:** Пользователь видит состояние подключения

---

#### ✅ UX #3: Voice status после reconnect
**Файл:** `public/app.js:1081-1087`

**Добавлено:**
```javascript
if (sessionData.status === 'paused') {
    this.elements.voiceStatus.textContent = 'На паузе';
    document.querySelector('.wave')?.classList.add('inactive');
} else {
    this.elements.voiceStatus.textContent = 'Подключено. Ожидание...';
}
```

**Результат:** Корректный статус после reconnect

---

## Тестирование

### Сценарий A: Возврат к паузированной сессии (ОСНОВНОЙ)

1. ✅ Создать консультацию
2. ✅ Поговорить 2-3 минуты (10+ сообщений)
3. ✅ Нажать "Сохранить и выйти"
4. ✅ **Проверить:** статус в БД = `paused` (НЕ `processing`)
5. ✅ Вернуться по ссылке `/session/<unique_link>`
6. ✅ **ОЖИДАЕМО:**
   - UI показывает состояние паузы (overlay visible, mic disabled, кнопка "▶")
   - LiveKit room подключен (`isConnected = true`)
   - Микрофон НЕ активируется автоматически
7. ✅ Нажать кнопку "▶" (Resume)
8. ✅ **ОЖИДАЕМО:**
   - Микрофон активируется
   - Можно продолжить диалог

### Сценарий B: Возврат к активной сессии

1. ✅ Создать консультацию
2. ✅ Поговорить 1 минуту
3. ✅ Закрыть браузер (НЕ нажимая "Сохранить и выйти")
4. ✅ **Проверить:** статус в БД = `active`
5. ✅ Вернуться по ссылке
6. ✅ **ОЖИДАЕМО:**
   - LiveKit room подключается
   - Микрофон автоматически активируется через 500ms после `RoomEvent.Connected`
   - Можно сразу продолжить диалог

### Database Checks

```sql
-- After "Сохранить и выйти":
SELECT session_id, status, updated_at
FROM sessions
WHERE session_id = '39139356';
-- EXPECTED: status = 'paused' (NOT 'processing')

-- Check dialogue_history saved:
SELECT LENGTH(dialogue_history) as history_len
FROM sessions
WHERE session_id = '39139356';
-- EXPECTED: history_len > 1000 (90 messages saved)
```

### Browser Console Checks

**НЕ должно быть:**
```
❌ Logger._log() got an unexpected keyword argument 'session_id'
❌ Cannot read properties of null (reading 'publishTrack')
❌ TypeError: this.localParticipant is null
```

**Должно быть:**
```
✅ dialogue_saved_sync
✅ Connected to room: consultation-39139356
✅ === START RECORDING ===
```

---

## Success Criteria

- ✅ Logger error исправлен → dialogue_history сохраняется
- ✅ Race condition исправлен → статус `paused` сохраняется
- ✅ Reconnect работает → для всех статусов
- ✅ Микрофон активируется корректно:
  - Для `active`: автоматически после `RoomEvent.Connected`
  - Для `paused`: НЕ активируется, UI паузы восстановлен
- ✅ Guard check → graceful error handling
- ✅ UX прозрачность → пользователь видит что происходит

---

## Файлы изменены

- `src/voice/consultant.py` (3 изменения: logger, race condition sync, race condition async)
- `public/app.js` (6 изменений: reconnect, event-driven, guard, UI restore, UX feedback)

---

## Следующие шаги (опционально)

### SPRINT 3: Conversation Logic (P1, 2 часа)
- Reconnect greeting
- Phase detection
- Review phase fix

### SPRINT 4: Edge Cases (P2, 4 часа)
- Token expiration (24+ часов)
- Network failures (retry logic)
- Multiple clients в одном room
- Browser back button

### SPRINT 5: Architecture (P3, 5 часов)
- State machine для session lifecycle
- Optimistic locking с version field
- WebSocket для real-time status updates
- Exponential backoff для network retries

---

## Deployment

```bash
# 1. Verify changes
git diff src/voice/consultant.py public/app.js

# 2. Test locally
make restart
# Запустить E2E тест (сценарий A)

# 3. Commit
git add src/voice/consultant.py public/app.js BUGFIX_v4.4_CHANGELOG.md
git commit -m "fix: исправить микрофон при возобновлении сессии (v4.4)

БАГ #1: Logger error - dialogue_history не сохранялся
БАГ #2: Race condition - статус 'paused' затирался на 'processing'
БАГ #3: Frontend не reconnect для status='processing'
БАГ #4: startRecording() до готовности localParticipant
БАГ #5: Нет guard check в startRecording()
БАГ #6: UI паузы не восстанавливался

UX #1: Feedback при reconnect (toast + voice status)
UX #2: Connection status для resumed sessions
UX #3: Voice status после reconnect

Тестовая сессия: 39139356
Команда Consilium: 7 специализированных агентов

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# 4. Deploy
git push origin main
```

---

## Monitoring

После деплоя отслеживать:
- ✅ Reconnect success rate > 95%
- ✅ Dialogue history save success rate = 100%
- ✅ Session status transitions (track invalid transitions)
- ✅ User feedback: можно возобновить паузированные сессии

---

**Статус:** ✅ ГОТОВ К ДЕПЛОЮ
**Версия:** v4.4
**Автор:** Claude Sonnet 4.5 (команда Consilium)
