"use strict";

const byId = (id) => document.getElementById(id);
const els = {
  avatar: byId("avatar"), callAvatar: byId("callAvatar"), companionName: byId("companionName"),
  voiceCardName: byId("voiceCardName"), callButtonName: byId("callButtonName"), composerCallName: byId("composerCallName"),
  footerName: byId("footerName"), callTitleName: byId("callTitleName"), captionCompanionName: byId("captionCompanionName"),
  readiness: byId("callReadiness"), readinessText: byId("callReadinessText"), callButton: byId("callButton"),
  messages: byId("messages"), input: byId("messageInput"), send: byId("sendButton"), mic: byId("micButton"),
  sound: byId("soundButton"), settings: byId("settingsButton"), install: byId("installButton"),
  modal: byId("settingsModal"), closeSettings: byId("closeSettings"), form: byId("settingsForm"),
  userName: byId("userNameInput"), companionNameInput: byId("companionNameInput"), about: byId("aboutUserInput"),
  memory: byId("memoryNotesInput"), style: byId("styleNotesInput"), faith: byId("faithModeInput"),
  autoSpeak: byId("autoSpeakInput"), voice: byId("voiceSelect"), voiceRate: byId("voiceRateInput"),
  voiceRateOutput: byId("voiceRateOutput"), realtimeVoice: byId("realtimeVoiceSelect"),
  realtimeSpeed: byId("realtimeSpeedInput"), realtimeSpeedOutput: byId("realtimeSpeedOutput"),
  eagerness: byId("turnEagernessSelect"), language: byId("voiceLanguageSelect"),
  export: byId("exportButton"), clear: byId("clearButton"), toast: byId("toast"),
  callStage: byId("callStage"), callPresence: byId("callPresence"), callStatus: byId("callStatus"),
  callHint: byId("callHint"), callTimer: byId("callTimer"), userCaption: byId("userCaption"),
  assistantCaption: byId("assistantCaption"), mute: byId("muteButton"), speaker: byId("speakerButton"),
  endCall: byId("endCallButton"), remoteAudio: byId("remoteAudio"),
};

const state = { settings: {}, messages: [], realtimeAvailable: false, voices: [], deferredInstall: null };
const call = {
  active: false, pc: null, dataChannel: null, stream: null, timer: null, startedAt: 0,
  muted: false, speakerMuted: false, userDrafts: new Map(), assistantDrafts: new Map(), saved: new Set(),
};
let typingNode = null;
let recognition = null;
let toastTimer = null;

async function request(path, options = {}) {
  const init = { credentials: "same-origin", ...options, headers: { ...(options.headers || {}) } };
  if (init.body && typeof init.body !== "string") {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(path, init);
  const type = response.headers.get("content-type") || "";
  const payload = type.includes("application/json") ? await response.json() : await response.text();
  if (response.status === 401) {
    location.assign("/login");
    throw new Error("Please sign in again.");
  }
  if (!response.ok) {
    const message = typeof payload === "object" ? payload.error : payload;
    throw new Error(message || `Request failed (${response.status}).`);
  }
  return payload;
}

function bool(value) { return value === true || String(value).toLowerCase() === "true"; }
function companion() { return state.settings.companion_name || "Khotso"; }
function initial(name) { return (name || "K").trim().charAt(0).toUpperCase() || "K"; }
function showToast(message) {
  clearTimeout(toastTimer);
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  toastTimer = setTimeout(() => els.toast.classList.add("hidden"), 4200);
}
function formatTime(value) {
  if (!value) return "";
  const normalized = value.includes("T") ? value : value.replace(" ", "T") + "Z";
  const date = new Date(normalized);
  return Number.isNaN(date.valueOf()) ? "" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function applyNames() {
  const name = companion();
  const letter = initial(name);
  [els.companionName, els.voiceCardName, els.callButtonName, els.composerCallName, els.footerName,
    els.callTitleName, els.captionCompanionName].forEach((el) => { if (el) el.textContent = name; });
  [els.avatar, els.callAvatar].forEach((el) => { if (el) el.textContent = letter; });
  document.title = `${name} — Voice Companion`;
}

function messageElement(item) {
  const article = document.createElement("article");
  article.className = `message ${item.role === "user" ? "user" : "assistant"}`;
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const source = item.source === "voice" ? " · voice call" : "";
  meta.textContent = `${item.role === "user" ? "You" : companion()}${source}${item.created_at ? ` · ${formatTime(item.created_at)}` : ""}`;
  const text = document.createElement("p");
  text.className = "message-text";
  text.textContent = item.content;
  bubble.append(meta, text);
  article.append(bubble);
  return article;
}

function renderMessages(scroll = true) {
  els.messages.replaceChildren(...state.messages.map(messageElement));
  if (typingNode) els.messages.append(typingNode);
  if (scroll) requestAnimationFrame(() => { els.messages.scrollTop = els.messages.scrollHeight; });
}

function showTyping() {
  const article = document.createElement("article");
  article.className = "message assistant";
  article.innerHTML = '<div class="message-bubble"><div class="message-meta">Khotso is thinking</div><div class="typing-dots" aria-label="Thinking"><span></span><span></span><span></span></div></div>';
  typingNode = article;
  renderMessages();
}
function hideTyping() { typingNode = null; renderMessages(); }

async function refreshState() {
  const data = await request("/api/state");
  state.settings = data.settings || {};
  state.messages = data.messages || [];
  state.realtimeAvailable = Boolean(data.realtime_available);
  state.voices = data.realtime_voices || [];
  applyNames();
  renderMessages();
  fillSettings();
  updateReadiness();
  updateSoundButton();
}

function updateReadiness() {
  const secure = window.isSecureContext || ["localhost", "127.0.0.1"].includes(location.hostname);
  let message = "Ready for a private live voice call.";
  let ready = true;
  if (!secure) { ready = false; message = "Open this website over HTTPS to use the microphone."; }
  else if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) { ready = false; message = "This browser does not support the required live-call features."; }
  else if (!state.realtimeAvailable) { ready = false; message = "Add the server-side OpenAI API key to enable live calls."; }
  els.callButton.disabled = !ready || call.active;
  els.readiness.classList.toggle("ready", ready);
  els.readiness.classList.toggle("not-ready", !ready);
  els.readinessText.textContent = message;
}

function resizeInput() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(130, els.input.scrollHeight)}px`;
}

async function sendMessage(message = els.input.value.trim()) {
  if (!message || els.send.disabled) return;
  const optimistic = { role: "user", content: message, source: "typed", created_at: new Date().toISOString() };
  state.messages.push(optimistic);
  els.input.value = "";
  resizeInput();
  els.send.disabled = true;
  showTyping();
  try {
    const data = await request("/api/chat", { method: "POST", body: { message } });
    state.messages.push({ role: "assistant", content: data.reply, source: "typed", created_at: new Date().toISOString() });
    hideTyping();
    if (bool(state.settings.auto_speak)) speak(data.reply);
  } catch (error) {
    state.messages = state.messages.filter((item) => item !== optimistic);
    hideTyping();
    els.input.value = message;
    resizeInput();
    showToast(error.message);
  } finally {
    els.send.disabled = false;
    els.input.focus();
  }
}

function speechVoices() { return window.speechSynthesis ? speechSynthesis.getVoices() : []; }
function populateDeviceVoices() {
  const selected = state.settings.voice_name || els.voice.value;
  const options = [new Option("Device default", "")];
  speechVoices().forEach((voice) => options.push(new Option(`${voice.name} — ${voice.lang}`, voice.name)));
  els.voice.replaceChildren(...options);
  els.voice.value = selected;
}
function speak(text) {
  if (!window.speechSynthesis || !text) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const chosen = speechVoices().find((voice) => voice.name === state.settings.voice_name);
  if (chosen) utterance.voice = chosen;
  utterance.rate = Number(state.settings.voice_rate || 0.95);
  speechSynthesis.speak(utterance);
}
function updateSoundButton() {
  const enabled = bool(state.settings.auto_speak);
  els.sound.textContent = enabled ? "🔊" : "🔇";
  els.sound.setAttribute("aria-pressed", String(enabled));
  els.sound.title = enabled ? "Mute spoken typed replies" : "Enable spoken typed replies";
}

function fillSettings() {
  const s = state.settings;
  els.userName.value = s.user_name || "Rorisang";
  els.companionNameInput.value = s.companion_name || "Khotso";
  els.about.value = s.about_user || "";
  els.memory.value = s.memory_notes || "";
  els.style.value = s.style_notes || "";
  els.faith.checked = bool(s.faith_mode);
  els.autoSpeak.checked = bool(s.auto_speak);
  els.voiceRate.value = s.voice_rate || "0.95";
  els.voiceRateOutput.value = Number(els.voiceRate.value).toFixed(2);
  els.realtimeVoice.value = s.realtime_voice || "cedar";
  els.realtimeSpeed.value = s.realtime_speed || "0.95";
  els.realtimeSpeedOutput.value = Number(els.realtimeSpeed.value).toFixed(2);
  els.eagerness.value = s.turn_eagerness || "low";
  els.language.value = s.voice_language || "auto";
  populateDeviceVoices();
  els.voice.value = s.voice_name || "";
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    user_name: els.userName.value, companion_name: els.companionNameInput.value,
    about_user: els.about.value, memory_notes: els.memory.value, style_notes: els.style.value,
    faith_mode: els.faith.checked, auto_speak: els.autoSpeak.checked, voice_name: els.voice.value,
    voice_rate: els.voiceRate.value, realtime_voice: els.realtimeVoice.value,
    realtime_speed: els.realtimeSpeed.value, turn_eagerness: els.eagerness.value,
    voice_language: els.language.value,
  };
  try {
    const data = await request("/api/settings", { method: "POST", body: payload });
    state.settings = data.settings;
    applyNames();
    updateSoundButton();
    els.modal.classList.add("hidden");
    showToast("Your companion settings were saved.");
  } catch (error) { showToast(error.message); }
}

async function toggleSound() {
  const enabled = !bool(state.settings.auto_speak);
  try {
    const data = await request("/api/settings", { method: "POST", body: { auto_speak: enabled } });
    state.settings = data.settings;
    updateSoundButton();
    if (!enabled && window.speechSynthesis) speechSynthesis.cancel();
  } catch (error) { showToast(error.message); }
}

function startDictation() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) { showToast("One-message dictation is not supported by this browser. Use the live call or type instead."); return; }
  if (recognition) { recognition.stop(); return; }
  recognition = new Recognition();
  recognition.lang = state.settings.voice_language === "fr" ? "fr-CA" : state.settings.voice_language === "es" ? "es" : "en-CA";
  recognition.interimResults = true;
  recognition.continuous = false;
  const original = els.input.value;
  recognition.onstart = () => { els.mic.classList.add("listening"); els.mic.setAttribute("aria-pressed", "true"); };
  recognition.onresult = (event) => {
    let words = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) words += event.results[index][0].transcript;
    els.input.value = `${original}${original ? " " : ""}${words}`.trimStart();
    resizeInput();
  };
  recognition.onerror = (event) => showToast(event.error === "not-allowed" ? "Microphone permission was denied." : "Dictation stopped before a message was captured.");
  recognition.onend = () => { recognition = null; els.mic.classList.remove("listening"); els.mic.setAttribute("aria-pressed", "false"); };
  recognition.start();
}

function callStatus(text, hint = "", presence = "connecting") {
  els.callStatus.textContent = text;
  els.callHint.textContent = hint;
  els.callPresence.dataset.state = presence;
}
function startTimer() {
  call.startedAt = Date.now();
  call.timer = setInterval(() => {
    const seconds = Math.floor((Date.now() - call.startedAt) / 1000);
    const value = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    els.callTimer.textContent = value;
    els.callTimer.dateTime = `PT${seconds}S`;
  }, 1000);
}
function waitForIce(pc) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const timeout = setTimeout(resolve, 5000);
    const listener = () => {
      if (pc.iceGatheringState === "complete") {
        clearTimeout(timeout); pc.removeEventListener("icegatheringstatechange", listener); resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", listener);
  });
}

async function saveVoice(role, content, eventId) {
  const text = String(content || "").trim();
  const id = String(eventId || `${role}-${Date.now()}-${text.slice(0, 30)}`);
  if (!text || call.saved.has(id)) return;
  call.saved.add(id);
  try { await request("/api/voice/message", { method: "POST", body: { role, content: text, event_id: id } }); }
  catch (error) { console.warn("Could not save voice transcript", error); call.saved.delete(id); }
}
function keyFor(event, fallback) { return event.item_id || event.response_id || event.item?.id || event.event_id || fallback; }
function transcriptFrom(item) {
  if (!item) return "";
  const parts = [];
  for (const content of item.content || []) {
    const text = content.transcript || content.text;
    if (typeof text === "string" && text.trim()) parts.push(text.trim());
  }
  return parts.join(" ").trim();
}

function handleRealtimeEvent(raw) {
  let event;
  try { event = JSON.parse(raw); } catch { return; }
  const type = event.type || "";
  if (type === "error") {
    const message = event.error?.message || "The live voice service reported an error.";
    showToast(message); callStatus("The call needs attention", message, "connecting"); return;
  }
  if (type === "session.created" || type === "session.updated") callStatus("Listening to you", "Speak naturally. You can interrupt at any time.", "listening");
  if (type.includes("speech_started")) callStatus("I’m listening", "Take your time and finish your thought.", "listening");
  if (type.includes("speech_stopped")) callStatus(`${companion()} is thinking`, "Your words are being understood.", "connecting");

  if (type.includes("input_audio_transcription.delta")) {
    const key = keyFor(event, "user");
    const text = (call.userDrafts.get(key) || "") + (event.delta || "");
    call.userDrafts.set(key, text); els.userCaption.textContent = text || "Listening…";
  }
  if (type.includes("input_audio_transcription.completed")) {
    const key = keyFor(event, "user");
    const text = event.transcript || call.userDrafts.get(key) || "";
    call.userDrafts.set(key, text); els.userCaption.textContent = text || "Your words will appear here.";
    void saveVoice("user", text, `user-${key}`);
  }

  if (type.includes("audio_transcript.delta")) {
    const key = keyFor(event, "assistant");
    const text = (call.assistantDrafts.get(key) || "") + (event.delta || "");
    call.assistantDrafts.set(key, text); els.assistantCaption.textContent = text || `${companion()} is speaking…`;
    callStatus(`${companion()} is speaking`, "You can interrupt naturally.", "speaking");
  }
  if (type.includes("audio_transcript.done")) {
    const key = keyFor(event, "assistant");
    const text = event.transcript || call.assistantDrafts.get(key) || "";
    call.assistantDrafts.set(key, text); els.assistantCaption.textContent = text || "His spoken reply will appear here.";
    void saveVoice("assistant", text, `assistant-${key}`);
  }
  if (type === "response.output_item.done" || type === "conversation.item.created") {
    const item = event.item;
    if (item?.role === "assistant") {
      const text = transcriptFrom(item);
      if (text) { els.assistantCaption.textContent = text; void saveVoice("assistant", text, `assistant-${item.id || event.event_id}`); }
    }
  }
  if (type === "response.done" || type.endsWith("audio.done")) callStatus("Listening to you", "Speak whenever you are ready.", "listening");
}

async function startCall() {
  if (call.active || els.callButton.disabled) return;
  call.active = true; updateReadiness();
  call.userDrafts.clear(); call.assistantDrafts.clear(); call.saved.clear();
  els.userCaption.textContent = "Your words will appear here.";
  els.assistantCaption.textContent = "His spoken reply will appear here.";
  els.callTimer.textContent = "00:00";
  els.callStage.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  callStatus("Preparing the private call…", "Your browser may ask for microphone permission.", "connecting");
  try {
    call.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    call.pc = new RTCPeerConnection();
    call.pc.ontrack = (event) => {
      els.remoteAudio.srcObject = event.streams[0];
      els.remoteAudio.muted = call.speakerMuted;
      void els.remoteAudio.play().catch(() => {});
    };
    call.pc.onconnectionstatechange = () => {
      if (["failed", "disconnected"].includes(call.pc?.connectionState)) {
        showToast("The voice connection was interrupted."); void endCall();
      }
    };
    call.stream.getTracks().forEach((track) => call.pc.addTrack(track, call.stream));
    call.dataChannel = call.pc.createDataChannel("oai-events");
    call.dataChannel.onopen = () => callStatus("Listening to you", "Speak naturally. You can interrupt at any time.", "listening");
    call.dataChannel.onmessage = (event) => handleRealtimeEvent(event.data);
    call.dataChannel.onerror = () => showToast("The live captions channel encountered a problem.");
    await call.pc.setLocalDescription(await call.pc.createOffer());
    await waitForIce(call.pc);
    const response = await fetch("/api/realtime/session", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/sdp" },
      body: call.pc.localDescription.sdp,
    });
    const answer = await response.text();
    if (!response.ok) {
      let message = answer;
      try { message = JSON.parse(answer).error || answer; } catch { /* text response */ }
      throw new Error(message || "The live call could not be created.");
    }
    await call.pc.setRemoteDescription({ type: "answer", sdp: answer });
    startTimer();
  } catch (error) {
    showToast(error.name === "NotAllowedError" ? "Microphone permission was denied. Allow it in your browser settings and try again." : error.message);
    await endCall(false);
  }
}

async function endCall(refresh = true) {
  if (!call.active && els.callStage.classList.contains("hidden")) return;
  call.active = false;
  clearInterval(call.timer); call.timer = null;
  try { call.dataChannel?.close(); } catch { /* already closed */ }
  try { call.pc?.close(); } catch { /* already closed */ }
  call.stream?.getTracks().forEach((track) => track.stop());
  call.pc = null; call.dataChannel = null; call.stream = null;
  els.remoteAudio.srcObject = null;
  els.callStage.classList.add("hidden");
  document.body.style.overflow = "";
  call.muted = false; call.speakerMuted = false;
  els.mute.setAttribute("aria-pressed", "false"); els.speaker.setAttribute("aria-pressed", "false");
  updateReadiness();
  if (refresh) {
    try { await refreshState(); } catch (error) { showToast(error.message); }
  }
}
function toggleMute() {
  call.muted = !call.muted;
  call.stream?.getAudioTracks().forEach((track) => { track.enabled = !call.muted; });
  els.mute.setAttribute("aria-pressed", String(call.muted));
  els.mute.querySelector(".control-label").textContent = call.muted ? "Unmute" : "Mute";
  callStatus(call.muted ? "Microphone muted" : "Listening to you", call.muted ? "Khotso cannot hear you until you unmute." : "Speak whenever you are ready.", call.muted ? "connecting" : "listening");
}
function toggleSpeaker() {
  call.speakerMuted = !call.speakerMuted;
  els.remoteAudio.muted = call.speakerMuted;
  els.speaker.setAttribute("aria-pressed", String(call.speakerMuted));
  els.speaker.querySelector(".control-label").textContent = call.speakerMuted ? "Unmute" : "Speaker";
}

function bindEvents() {
  els.send.addEventListener("click", () => void sendMessage());
  els.input.addEventListener("input", resizeInput);
  els.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); }
  });
  document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => void sendMessage(button.dataset.prompt)));
  els.mic.addEventListener("click", startDictation);
  els.sound.addEventListener("click", () => void toggleSound());
  els.settings.addEventListener("click", () => { fillSettings(); els.modal.classList.remove("hidden"); });
  els.closeSettings.addEventListener("click", () => els.modal.classList.add("hidden"));
  els.modal.addEventListener("click", (event) => { if (event.target === els.modal) els.modal.classList.add("hidden"); });
  els.form.addEventListener("submit", saveSettings);
  els.voiceRate.addEventListener("input", () => { els.voiceRateOutput.value = Number(els.voiceRate.value).toFixed(2); });
  els.realtimeSpeed.addEventListener("input", () => { els.realtimeSpeedOutput.value = Number(els.realtimeSpeed.value).toFixed(2); });
  els.export.addEventListener("click", () => location.assign("/api/export"));
  els.clear.addEventListener("click", async () => {
    if (!confirm("Permanently clear the saved conversation transcript? Your profile and memory settings will remain.")) return;
    try { await request("/api/clear", { method: "POST", body: { confirm: "CLEAR" } }); state.messages = []; renderMessages(); showToast("The conversation history was cleared."); }
    catch (error) { showToast(error.message); }
  });
  els.callButton.addEventListener("click", () => void startCall());
  els.endCall.addEventListener("click", () => void endCall());
  els.mute.addEventListener("click", toggleMute);
  els.speaker.addEventListener("click", toggleSpeaker);
  els.install.addEventListener("click", async () => {
    if (!state.deferredInstall) return;
    state.deferredInstall.prompt(); await state.deferredInstall.userChoice;
    state.deferredInstall = null; els.install.classList.add("hidden");
  });
  window.addEventListener("beforeinstallprompt", (event) => { event.preventDefault(); state.deferredInstall = event; els.install.classList.remove("hidden"); });
  window.addEventListener("appinstalled", () => { state.deferredInstall = null; els.install.classList.add("hidden"); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.modal.classList.contains("hidden")) els.modal.classList.add("hidden");
  });
  if (window.speechSynthesis) speechSynthesis.addEventListener?.("voiceschanged", populateDeviceVoices);
}

async function boot() {
  bindEvents();
  resizeInput();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(console.warn);
  try { await refreshState(); }
  catch (error) { showToast(error.message); els.readinessText.textContent = "The website could not load its private state."; }
}

document.addEventListener("DOMContentLoaded", boot);
