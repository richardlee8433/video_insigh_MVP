const BASE_URL = import.meta.env.VITE_API_URL || "";

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
