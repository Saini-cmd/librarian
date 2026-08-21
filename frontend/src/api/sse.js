export async function consumeSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (line.startsWith("data:")) {
          const payload = line.slice(5).trim();
          if (!payload) continue;
          let parsed;
          try {
            parsed = JSON.parse(payload);
          } catch {
            continue;
          }
          onEvent(parsed);
        }
      }
    }
  }
}

export async function readError(response) {
  /* Best-effort extraction from a non-SSE error response. Returns
     `{ message, quota }` — `quota` is `{group, used, limit, resets_at}` when
     the response is a usage-cap 429 (the ledger-based daily-limit gate in
     `backend/usage.py`), otherwise null. Handles FastAPI's `{"detail": "..."}`
     and the 429 shape `{"detail": {"detail", "group", "used", "limit",
     "resets_at"}}`. */
  if (!response) return { message: "Request failed", quota: null };
  let body = null;
  try {
    body = await response.json();
  } catch {
    // non-JSON error body — fall through to the generic message
  }
  const d = body?.detail;
  if (d && typeof d === "object") {
    const msg =
      typeof d.detail === "string" ? d.detail : `Request failed (HTTP ${response.status})`;
    const isQuota =
      response.status === 429 && typeof d.used === "number" && typeof d.limit === "number";
    const quota = isQuota
      ? { group: d.group, used: d.used, limit: d.limit, resets_at: d.resets_at }
      : null;
    return { message: quota ? `${msg} (${quota.used}/${quota.limit} used)` : msg, quota };
  }
  if (typeof d === "string") return { message: d, quota: null };
  return { message: body?.message || `Request failed (HTTP ${response.status})`, quota: null };
}
