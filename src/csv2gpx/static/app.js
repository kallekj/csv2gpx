const uploadForm = document.querySelector("#upload-form");
const exportForm = document.querySelector("#export-form");
const message = document.querySelector("#message");
const video = document.querySelector("#video");
const logRange = document.querySelector("#log-range");
const videoRange = document.querySelector("#video-range");
const overlap = document.querySelector("#overlap");
const offset = document.querySelector("#offset");
const trimStart = document.querySelector("#trim-start");
const trimEnd = document.querySelector("#trim-end");
const exportButton = document.querySelector("#export-button");
const canvas = document.querySelector("#track-canvas");

let currentSession = null;

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("Analyzing files...", "muted");
  disableControls(true);

  const formData = new FormData(uploadForm);
  try {
    const response = await fetch("/api/session", {
      method: "POST",
      body: formData,
    });
    const payload = await parseJsonResponse(response);
    currentSession = payload;
    renderSession(payload);
    setMessage(statusText(payload.alignment.status), payload.alignment.status === "aligned" ? "ok" : "warn");
  } catch (error) {
    setMessage(error.message, "error");
  }
});

offset.addEventListener("change", async () => {
  if (!currentSession) return;
  try {
    const response = await fetch(
      `/api/session/${currentSession.sessionId}/alignment?offset_seconds=${encodeURIComponent(offset.value || "0")}`,
    );
    const payload = await parseJsonResponse(response);
    currentSession = payload;
    renderSession(payload);
    setMessage(statusText(payload.alignment.status), payload.alignment.status === "aligned" ? "ok" : "warn");
  } catch (error) {
    setMessage(error.message, "error");
  }
});

exportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentSession) return;

  const formData = new FormData();
  formData.append("session_id", currentSession.sessionId);
  formData.append("start_time", localToIso(trimStart.value));
  formData.append("end_time", localToIso(trimEnd.value));

  try {
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
    const filename = filenameFromDisposition(disposition) || "aligned-log.gpx";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMessage("GPX exported.", "ok");
  } catch (error) {
    setMessage(error.message, "error");
  }
});

async function parseJsonResponse(response) {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed.");
  }
  return payload;
}

function renderSession(payload) {
  video.src = payload.videoUrl;
  logRange.textContent = `${formatShort(payload.log.start)} to ${formatShort(payload.log.end)}`;
  videoRange.textContent = payload.alignment.videoStart
    ? `${formatShort(payload.alignment.videoStart)} to ${formatShort(payload.alignment.videoEnd)}`
    : "No timestamp";
  overlap.textContent =
    payload.alignment.overlapSeconds > 0 ? `${Math.round(payload.alignment.overlapSeconds)} s` : "-";

  offset.disabled = payload.video.creationTime === null;
  trimStart.disabled = false;
  trimEnd.disabled = false;
  exportButton.disabled = payload.alignment.exportStart === null || payload.alignment.exportEnd === null;

  if (payload.alignment.exportStart && payload.alignment.exportEnd) {
    trimStart.value = isoToLocalInput(payload.alignment.exportStart);
    trimEnd.value = isoToLocalInput(payload.alignment.exportEnd);
  } else {
    trimStart.value = isoToLocalInput(payload.log.start);
    trimEnd.value = isoToLocalInput(payload.log.end);
  }

  drawTrack(payload.log.preview);
}

function disableControls(disabled) {
  offset.disabled = disabled;
  trimStart.disabled = disabled;
  trimEnd.disabled = disabled;
  exportButton.disabled = disabled;
}

function drawTrack(points) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#111827";
  ctx.fillRect(0, 0, width, height);

  if (!points || points.length < 2) return;

  const lats = points.map((point) => point.lat);
  const lons = points.map((point) => point.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const pad = 34;
  const latSpan = maxLat - minLat || 1;
  const lonSpan = maxLon - minLon || 1;

  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.lineWidth = 1;
  for (let x = pad; x <= width - pad; x += 70) {
    ctx.beginPath();
    ctx.moveTo(x, pad);
    ctx.lineTo(x, height - pad);
    ctx.stroke();
  }
  for (let y = pad; y <= height - pad; y += 70) {
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(width - pad, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "#22c55e";
  ctx.lineWidth = 4;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = pad + ((point.lon - minLon) / lonSpan) * (width - pad * 2);
    const y = height - pad - ((point.lat - minLat) / latSpan) * (height - pad * 2);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function isoToLocalInput(value) {
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 19);
}

function localToIso(value) {
  return new Date(value).toISOString();
}

function formatShort(value) {
  if (!value) return "-";
  return value.replace("T", " ").replace("Z", "");
}

function statusText(status) {
  if (status === "aligned") return "Alignment ready.";
  if (status === "missing_video_time") return "Video start time missing. Set the export range manually.";
  if (status === "no_overlap") return "No timestamp overlap. Adjust the offset.";
  return "Ready.";
}

function filenameFromDisposition(disposition) {
  const match = disposition.match(/filename="([^"]+)"/);
  return match ? match[1] : null;
}

function setMessage(text, tone) {
  message.textContent = text;
  message.dataset.tone = tone;
}
