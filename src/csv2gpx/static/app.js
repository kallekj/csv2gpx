const uploadForm = document.querySelector("#upload-form");
const analyzeButton = document.querySelector("#analyze-button");
const cancelButton = document.querySelector("#cancel-button");
const logFile = document.querySelector("#log-file");
const videoFile = document.querySelector("#video-file");
const message = document.querySelector("#message");
const progressBar = document.querySelector("#progress-bar");
const video = document.querySelector("#video");
const logRange = document.querySelector("#log-range");
const videoRange = document.querySelector("#video-range");
const exportRange = document.querySelector("#export-range");
const offset = document.querySelector("#offset");
const manualStartField = document.querySelector("#manual-start-field");
const manualLogStart = document.querySelector("#manual-log-start");
const exportForm = document.querySelector("#export-form");
const filename = document.querySelector("#filename");
const exportButton = document.querySelector("#export-button");
const timeline = document.querySelector("#timeline");
const inHandle = document.querySelector("#in-handle");
const outHandle = document.querySelector("#out-handle");
const selectionFill = document.querySelector("#selection-fill");
const playhead = document.querySelector("#playhead");
const currentTime = document.querySelector("#current-time");
const videoDuration = document.querySelector("#video-duration");
const selectionDuration = document.querySelector("#selection-duration");
const setInButton = document.querySelector("#set-in");
const setOutButton = document.querySelector("#set-out");
const columnsList = document.querySelector("#columns-list");
const columnCount = document.querySelector("#column-count");
const selectAllColumns = document.querySelector("#select-all-columns");
const selectNoColumns = document.querySelector("#select-no-columns");
const COLUMN_PREFS_KEY = "csv2gpx:selectedColumns";

let currentSession = null;
let activeJobId = null;
let activeRequest = null;
let pollTimer = null;
let localVideoUrl = null;

logFile.addEventListener("change", prefillLocalFilename);

videoFile.addEventListener("change", () => {
  if (localVideoUrl) URL.revokeObjectURL(localVideoUrl);
  const file = videoFile.files[0];
  if (!file) return;
  localVideoUrl = URL.createObjectURL(file);
  video.src = localVideoUrl;
  prefillLocalFilename();
});

video.addEventListener("loadedmetadata", () => {
  const duration = safeDuration();
  setTimelineLimits(duration);
  inHandle.value = "0";
  outHandle.value = String(duration);
  renderTimeline();
});

video.addEventListener("timeupdate", renderTimeline);

uploadForm.addEventListener("submit", (event) => {
  event.preventDefault();
  startAnalysis();
});

cancelButton.addEventListener("click", async () => {
  if (activeRequest) activeRequest.abort();
  if (pollTimer) clearTimeout(pollTimer);
  if (activeJobId) {
    try {
      await fetch(`/api/jobs/${activeJobId}`, { method: "DELETE" });
    } catch {
      // The user already asked to cancel; a failed cleanup request should not trap the UI.
    }
  }
  setBusy(false);
  setProgress(0);
  setMessage("Analysis cancelled.", "warn");
});

offset.addEventListener("change", async () => {
  if (!currentSession) return;
  try {
    const response = await fetch(
      `/api/session/${currentSession.sessionId}/alignment?offset_seconds=${encodeURIComponent(offset.value || "0")}`,
    );
    const payload = await parseJsonResponse(response);
    currentSession = payload;
    setInitialClipFromAlignment(payload);
    renderSession(payload);
  } catch (error) {
    setMessage(error.message, "error");
  }
});

inHandle.addEventListener("input", () => {
  if (Number(inHandle.value) > Number(outHandle.value)) inHandle.value = outHandle.value;
  renderTimeline();
});

outHandle.addEventListener("input", () => {
  if (Number(outHandle.value) < Number(inHandle.value)) outHandle.value = inHandle.value;
  renderTimeline();
});

timeline.addEventListener("click", (event) => {
  if (event.target instanceof HTMLInputElement) return;
  const duration = safeDuration();
  if (duration <= 0) return;
  const rect = timeline.getBoundingClientRect();
  const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
  video.currentTime = ratio * duration;
});

setInButton.addEventListener("click", () => {
  inHandle.value = String(Math.min(video.currentTime, Number(outHandle.value)));
  renderTimeline();
});

setOutButton.addEventListener("click", () => {
  outHandle.value = String(Math.max(video.currentTime, Number(inHandle.value)));
  renderTimeline();
});

manualLogStart.addEventListener("change", renderTimeline);

selectAllColumns.addEventListener("click", () => setColumnChecks(true));
selectNoColumns.addEventListener("click", () => setColumnChecks(false));

exportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentSession) return;

  const range = selectedLogRange();
  if (!range) {
    setMessage("Select a valid video range before exporting.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("session_id", currentSession.sessionId);
  formData.append("start_time", range.start);
  formData.append("end_time", range.end);
  formData.append("filename", filename.value || currentSession.log.defaultFilename);
  const columns = selectedColumns();
  saveColumnPreferences();
  columns.forEach((column) => formData.append("selected_columns", column));

  try {
    setMessage("Exporting GPX...", "muted");
    const response = await fetch("/api/export", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.detail || "Export failed.");
    }

    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const downloadName = filenameFromDisposition(disposition) || sanitizeFilename(filename.value);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = downloadName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMessage("GPX exported.", "ok");
  } catch (error) {
    setMessage(error.message, "error");
  }
});

function startAnalysis() {
  if (!logFile.files[0] || !videoFile.files[0]) return;
  if (pollTimer) clearTimeout(pollTimer);
  currentSession = null;
  activeJobId = null;
  setBusy(true);
  setProgress(0);
  setMessage("Uploading files...", "muted");

  const formData = new FormData(uploadForm);
  const request = new XMLHttpRequest();
  activeRequest = request;

  request.upload.addEventListener("progress", (event) => {
    if (!event.lengthComputable) return;
    setProgress(Math.round((event.loaded / event.total) * 50));
  });

  request.addEventListener("load", () => {
    activeRequest = null;
    try {
      const payload = JSON.parse(request.responseText);
      if (request.status < 200 || request.status >= 300) {
        throw new Error(payload.detail || "Upload failed.");
      }
      activeJobId = payload.jobId;
      renderJob(payload);
      pollJob(payload.jobId);
    } catch (error) {
      setBusy(false);
      setMessage(error.message, "error");
    }
  });

  request.addEventListener("error", () => {
    activeRequest = null;
    setBusy(false);
    setMessage("Upload failed.", "error");
  });

  request.addEventListener("abort", () => {
    activeRequest = null;
  });

  request.open("POST", "/api/jobs");
  request.send(formData);
}

async function pollJob(jobId) {
  try {
    const payload = await parseJsonResponse(await fetch(`/api/jobs/${jobId}`));
    renderJob(payload);
    if (payload.status === "ready") {
      setBusy(false);
      currentSession = payload.session;
      setInitialClipFromAlignment(payload.session);
      renderSession(payload.session);
      setMessage(statusText(payload.session.alignment.status), payload.session.alignment.status === "aligned" ? "ok" : "warn");
      return;
    }
    if (payload.status === "failed") {
      setBusy(false);
      setMessage(payload.error || "Analysis failed.", "error");
      return;
    }
    if (payload.status === "cancelled") {
      setBusy(false);
      setMessage("Analysis cancelled.", "warn");
      return;
    }
    pollTimer = setTimeout(() => pollJob(jobId), 500);
  } catch (error) {
    setBusy(false);
    setMessage(error.message, "error");
  }
}

async function parseJsonResponse(response) {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed.");
  }
  return payload;
}

function renderJob(payload) {
  setProgress(payload.progress || 0);
  if (payload.message) setMessage(payload.message, "muted");
}

function renderSession(payload) {
  logRange.textContent = `${formatShort(payload.log.start)} to ${formatShort(payload.log.end)}`;
  videoRange.textContent = payload.alignment.videoStart
    ? `${formatShort(payload.alignment.videoStart)} to ${formatShort(payload.alignment.videoEnd)}`
    : "No timestamp";

  offset.disabled = payload.video.creationTime === null;
  manualStartField.hidden = payload.video.creationTime !== null;
  manualLogStart.disabled = payload.video.creationTime !== null;
  if (payload.video.creationTime === null && !manualLogStart.value) {
    manualLogStart.value = isoToLocalInput(payload.log.start);
  }

  filename.disabled = false;
  if (!filename.value) filename.value = payload.log.defaultFilename;
  exportButton.disabled = false;
  inHandle.disabled = false;
  outHandle.disabled = false;
  setInButton.disabled = false;
  setOutButton.disabled = false;
  selectAllColumns.disabled = false;
  selectNoColumns.disabled = false;
  renderColumns(payload.log.availableColumns);
  renderTimeline();
}

function setInitialClipFromAlignment(payload) {
  const duration = safeDuration() || payload.video.durationSeconds || 0;
  setTimelineLimits(duration);

  if (payload.alignment.exportStart && payload.alignment.exportEnd && payload.alignment.videoStart) {
    const videoStart = new Date(payload.alignment.videoStart).getTime();
    const exportStart = new Date(payload.alignment.exportStart).getTime();
    const exportEnd = new Date(payload.alignment.exportEnd).getTime();
    inHandle.value = String(clamp((exportStart - videoStart) / 1000, 0, duration));
    outHandle.value = String(clamp((exportEnd - videoStart) / 1000, 0, duration));
  } else {
    inHandle.value = "0";
    outHandle.value = String(duration);
  }
}

function renderColumns(columns) {
  const preferences = loadColumnPreferences();
  columnsList.innerHTML = "";
  columnCount.textContent = `${columns.length} columns`;
  for (const column of columns) {
    const label = document.createElement("label");
    label.className = "column-option";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = column.name;
    checkbox.checked = Object.hasOwn(preferences, column.name)
      ? preferences[column.name]
      : true;
    checkbox.addEventListener("change", saveColumnPreferences);

    const text = document.createElement("span");
    text.textContent = column.name;

    const tag = document.createElement("small");
    tag.textContent = column.tag;

    label.append(checkbox, text, tag);
    columnsList.append(label);
  }
}

function renderTimeline() {
  const duration = safeDuration();
  const current = duration > 0 ? video.currentTime : 0;
  const start = Number(inHandle.value || 0);
  const end = Number(outHandle.value || 0);
  const startPct = duration > 0 ? (start / duration) * 100 : 0;
  const endPct = duration > 0 ? (end / duration) * 100 : 0;
  const playPct = duration > 0 ? (current / duration) * 100 : 0;

  selectionFill.style.left = `${startPct}%`;
  selectionFill.style.width = `${Math.max(0, endPct - startPct)}%`;
  playhead.style.left = `${playPct}%`;
  currentTime.textContent = formatDuration(current);
  videoDuration.textContent = formatDuration(duration);
  selectionDuration.textContent = `Selection: ${formatDuration(Math.max(0, end - start))}`;

  const range = selectedLogRange();
  exportRange.textContent = range ? `${formatShort(range.start)} to ${formatShort(range.end)}` : "-";
}

function selectedLogRange() {
  if (!currentSession) return null;
  const startSeconds = Number(inHandle.value || 0);
  const endSeconds = Number(outHandle.value || 0);
  if (endSeconds <= startSeconds) return null;

  if (currentSession.alignment.videoStart) {
    const videoStart = new Date(currentSession.alignment.videoStart).getTime();
    return {
      start: new Date(videoStart + startSeconds * 1000).toISOString(),
      end: new Date(videoStart + endSeconds * 1000).toISOString(),
    };
  }

  if (!manualLogStart.value) return null;
  const start = new Date(manualLogStart.value).getTime();
  const durationMs = (endSeconds - startSeconds) * 1000;
  return {
    start: new Date(start).toISOString(),
    end: new Date(start + durationMs).toISOString(),
  };
}

function setTimelineLimits(duration) {
  for (const handle of [inHandle, outHandle]) {
    handle.min = "0";
    handle.max = String(duration);
    handle.step = "0.1";
  }
}

function selectedColumns() {
  return [...columnsList.querySelectorAll("input[type='checkbox']:checked")].map((input) => input.value);
}

function setColumnChecks(checked) {
  columnsList.querySelectorAll("input[type='checkbox']").forEach((input) => {
    input.checked = checked;
  });
  saveColumnPreferences();
}

function loadColumnPreferences() {
  try {
    const parsed = JSON.parse(localStorage.getItem(COLUMN_PREFS_KEY) || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function saveColumnPreferences() {
  const preferences = {};
  columnsList.querySelectorAll("input[type='checkbox']").forEach((input) => {
    preferences[input.value] = input.checked;
  });
  localStorage.setItem(COLUMN_PREFS_KEY, JSON.stringify(preferences));
}

function setBusy(busy) {
  analyzeButton.disabled = busy;
  cancelButton.disabled = !busy;
}

function setProgress(value) {
  progressBar.style.width = `${clamp(value, 0, 100)}%`;
}

function prefillLocalFilename() {
  if (filename.value || !logFile.files[0] || !videoFile.files[0]) return;
  filename.value = sanitizeFilename(`${stem(logFile.files[0].name)}_${stem(videoFile.files[0].name)}.gpx`);
}

function safeDuration() {
  return Number.isFinite(video.duration) ? video.duration : Number(outHandle.max || 0);
}

function isoToLocalInput(value) {
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 19);
}

function formatShort(value) {
  if (!value) return "-";
  return value.replace("T", " ").replace("Z", "");
}

function formatDuration(seconds) {
  const safe = Math.max(0, seconds || 0);
  const minutes = Math.floor(safe / 60);
  const wholeSeconds = Math.floor(safe % 60);
  const tenths = Math.floor((safe % 1) * 10);
  return `${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}.${tenths}`;
}

function statusText(status) {
  if (status === "aligned") return "Alignment ready.";
  if (status === "missing_video_time") return "Video start time missing. Set the log start manually.";
  if (status === "no_overlap") return "No timestamp overlap. Adjust the offset.";
  return "Ready.";
}

function filenameFromDisposition(disposition) {
  const match = disposition.match(/filename="([^"]+)"/);
  return match ? match[1] : null;
}

function sanitizeFilename(value) {
  const cleaned = value.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "");
  return cleaned.toLowerCase().endsWith(".gpx") ? cleaned : `${cleaned || "aligned-log"}.gpx`;
}

function stem(value) {
  return value.replace(/\.[^/.]+$/, "");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function setMessage(text, tone) {
  message.textContent = text;
  message.dataset.tone = tone;
}
