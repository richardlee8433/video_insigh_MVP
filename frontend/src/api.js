const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function uploadVideo(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/analyze`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  const data = await res.json();
  return data.job_id;
}

export async function getStatus(jobId) {
  const res = await fetch(`${BASE_URL}/status/${jobId}`);
  if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
  return res.json();
}

export async function getAudit(jobId) {
  const res = await fetch(`${BASE_URL}/audit/${jobId}`);
  if (!res.ok) throw new Error(`Audit fetch failed: ${res.status}`);
  return res.json();
}

export async function startStreaming(jobId, onToken, onDone, onError) {
  try {
    const response = await fetch(`${BASE_URL}/analyze-stream/${jobId}`, {
      method: "POST",
    });
    if (!response.ok) throw new Error(`Stream failed: ${response.status}`);
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulated = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      const lines = chunk.split("\n");
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const token = line.slice(6);
          accumulated += token;
          onToken(accumulated);
        }
      }
    }
    onDone(accumulated);
  } catch (err) {
    onError(err);
  }
}

export function pollUntilDone(jobId, onDone, onError, onProgress = null, interval = 2000) {
  const timer = setInterval(async () => {
    try {
      const { status, stage, result } = await getStatus(jobId);
      if (onProgress) onProgress({ status, stage });
      if (status === "done") {
        clearInterval(timer);
        onDone(result);
      } else if (status === "error") {
        clearInterval(timer);
        onError(result);
      }
    } catch (err) {
    clearInterval(timer);
    onError(err);
  }
}, interval);
return () => clearInterval(timer);
}

export async function analyzeLiveFrame(frameBase64, frameHash, jobId = null) {
const res = await fetch(`${BASE_URL}/analyze-live-frame`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ frame: frameBase64, hash: frameHash, job_id: jobId }),
});
if (!res.ok) throw new Error(`Live analysis failed: ${res.status}`);
return res.json();
}
