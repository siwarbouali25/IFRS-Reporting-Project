:host {
  --acid: #d6f000;
  --acid-bg: rgba(214, 240, 0, 0.12);
  --acid-border: rgba(214, 240, 0, 0.30);

  --accent: #4d9fff;
  --accent-bg: rgba(77, 159, 255, 0.12);
  --accent-border: rgba(77, 159, 255, 0.30);

  --warn: #ffb454;
  --warn-bg: rgba(255, 180, 84, 0.10);
  --warn-border: rgba(255, 180, 84, 0.30);

  --card: rgba(19, 19, 19, 0.95);
  --panel: rgba(10, 10, 10, 0.98);
  --border: rgba(255, 255, 255, 0.09);
  --muted: #7a7a8a;
  --text: #f0f0f0;

  font-family: 'Inter', 'DM Sans', system-ui, sans-serif;
  color: var(--text);
}

.assistant {
  display: grid;
  grid-template-columns: 260px 1fr;
  height: 100vh;
  box-sizing: border-box;
  background:
    radial-gradient(ellipse 60% 40% at 100% 0%, rgba(77, 159, 255, 0.08), transparent),
    var(--panel);
}

/* ---------------- history rail ---------------- */
.history {
  border-right: 1px solid var(--border);
  padding: 18px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.new-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px;
  border-radius: 12px;
  border: 1px solid var(--acid-border);
  background: var(--acid-bg);
  color: var(--acid);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.new-btn:hover { background: rgba(214, 240, 0, 0.2); }

.history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  min-height: 0;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  text-align: left;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.12s, border-color 0.12s;
}
.history-item:hover { background: rgba(255, 255, 255, 0.04); }
.history-item.active {
  background: var(--card);
  border-color: var(--border);
}
.history-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-bank {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--accent);
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  padding: 1px 6px;
}
.history-empty {
  color: var(--muted);
  font-size: 13px;
  padding: 8px 12px;
}

/* ---------------- chat column ---------------- */
.chat {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 28px;
  border-bottom: 1px solid var(--border);
  background: rgba(10, 10, 10, 0.6);
  backdrop-filter: blur(8px);
}
.chat-title { display: flex; align-items: center; gap: 14px; }
.header-mark {
  width: 40px; height: 40px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 13px; color: #000;
  background: linear-gradient(135deg, var(--acid), var(--accent));
}
.chat-header h1 { font-size: 19px; margin: 0; }
.chat-header p { color: var(--muted); font-size: 13px; margin: 3px 0 0; }

.scope {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.scope select {
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 13px;
  min-width: 210px;
}
.scope select:disabled { opacity: 0.5; }

/* ---------------- messages ---------------- */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 26px 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 0;
  scroll-behavior: smooth;
}

.row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  animation: slideIn 0.28s ease;
}
.row.user { justify-content: flex-end; }

@keyframes slideIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.avatar {
  flex-shrink: 0;
  width: 32px; height: 32px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700;
}
.assistant-avatar {
  color: #000;
  background: linear-gradient(135deg, var(--acid), var(--accent));
}
.user-avatar {
  color: var(--accent);
  background: var(--accent-bg);
  border: 1px solid var(--accent-border);
}

.bubble {
  width: fit-content;
  max-width: 30rem;
  min-width: 0;
  padding: 13px 15px;
  border-radius: 16px 16px 16px 4px;
  font-size: 14px;
  line-height: 1.6;
  background: var(--card);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.row.user .bubble {
  border-radius: 16px 16px 4px 16px;
  background: var(--accent-bg);
  border-color: var(--accent-border);
}
.bubble-text { white-space: pre-wrap; word-break: break-word; max-width: 100%; }
.bubble-text strong { color: #fff; font-weight: 600; }
.bubble-text code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12.5px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 1px 5px;
}

.fallback-note {
  margin-top: 10px;
  font-size: 12px;
  color: var(--warn);
  display: flex;
  align-items: center;
  gap: 6px;
}

/* data gaps */
.gaps {
  width: 0;
  min-width: 100%;
  box-sizing: border-box;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--warn-bg);
  border: 1px solid var(--warn-border);
}
.gaps-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--warn);
  margin-bottom: 8px;
}
.gap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 0;
  font-size: 12px;
  border-top: 1px solid rgba(255, 180, 84, 0.15);
}
.gap:first-of-type { border-top: none; }
.gap-field {
  color: var(--text);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11.5px;
}
.gap-instruction { color: var(--muted); }

/* citations */
.citations {
  width: 0;
  min-width: 100%;
  box-sizing: border-box;
  margin-top: 12px;
  padding-top: 11px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  font-size: 11px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0 11px;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.chip i {
  color: var(--accent);
  font-size: 11px;
}
.chip:hover {
  color: var(--text);
  border-color: var(--accent-border);
  background: var(--accent-bg);
}

/* typing */
.typing { display: flex; gap: 4px; padding: 4px 2px; }
.typing span {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--muted);
  animation: blink 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 60%, 100% { opacity: 0.25; }
  30% { opacity: 1; }
}

/* welcome */
.welcome {
  margin: auto;
  max-width: 580px;
  text-align: center;
}
.welcome-mark {
  width: 56px; height: 56px;
  margin: 0 auto 18px;
  border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: #000;
  background: linear-gradient(135deg, var(--acid), var(--accent));
  box-shadow: 0 8px 30px rgba(77, 159, 255, 0.25);
}
.welcome h2 { margin: 0 0 8px; font-size: 22px; }
.welcome p { color: var(--muted); font-size: 14px; margin: 0 0 22px; }
.suggestions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.suggestions button {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 15px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.15s;
}
.suggestions button i { color: var(--accent); }
.suggestions button:hover {
  border-color: var(--accent-border);
  transform: translateY(-2px);
}

/* ---------------- composer ---------------- */
.error-bar {
  margin: 0 28px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(255, 90, 90, 0.1);
  border: 1px solid rgba(255, 90, 90, 0.3);
  color: #ff8a8a;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 16px 28px 22px;
  border-top: 1px solid var(--border);
}
.composer textarea {
  flex: 1;
  resize: none;
  height: auto;
  max-height: 160px;
  overflow-y: auto;
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 13px 16px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  transition: border-color 0.15s;
}
.composer textarea:focus {
  outline: none;
  border-color: var(--accent-border);
}
.send-btn {
  flex-shrink: 0;
  width: 48px; height: 48px;
  border-radius: 14px;
  border: 1px solid var(--acid-border);
  background: var(--acid);
  color: #000;
  font-size: 16px;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
}
.send-btn:hover:not(:disabled) { transform: scale(1.05); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 900px) {
  .assistant { grid-template-columns: 1fr; }
  .history { display: none; }
}
