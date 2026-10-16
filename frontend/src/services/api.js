const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // Non-JSON error body; fall through to the generic message.
  }
  return `Request failed (${response.status})`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, options);
  } catch {
    throw new Error("Could not reach the server. Is the backend running?");
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.status === 204 ? null : response.json();
}

export const statsPath = (tzOffsetMinutes) => `/api/stats?tz_offset_minutes=${tzOffsetMinutes}`;

export const listDocuments = () => request("/api/documents");
export const deleteDocument = (id) => request(`/api/documents/${id}`, { method: "DELETE" });
export const listConversations = () => request("/api/conversations");
export const getConversation = (id) => request(`/api/conversations/${id}`);
export const deleteConversation = (id) => request(`/api/conversations/${id}`, { method: "DELETE" });
export const getStats = () => request(statsPath(new Date().getTimezoneOffset()));

export async function checkHealth() {
  try {
    const response = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(4000) });
    return response.ok;
  } catch {
    return false;
  }
}

export function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/upload", { method: "POST", body: form });
}

export function createSseParser(onEvent) {
  let buffer = "";
  const feed = (text) => {
    // SSE lines may end in CRLF, LF or a lone CR. A CR at the very end of a read may be the first
    // half of a CRLF split across reads, so it stays in the buffer until the next read arrives.
    buffer = (buffer + text).replace(/\r\n/g, "\n").replace(/\r(?!$)/g, "\n");
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      const data = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) onEvent(event, JSON.parse(data.join("\n")));
    }
  };
  // At end of stream a trailing CR can no longer be half of a CRLF: treat it as a line ending.
  feed.end = () => {
    if (buffer.endsWith("\r")) buffer = `${buffer.slice(0, -1)}\n`;
    feed("");
  };
  return feed;
}

export async function streamQuery({ question, conversationId, onEvent, signal }) {
  let response;
  try {
    response = await fetch(`${BASE_URL}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
      signal,
    });
  } catch {
    throw new Error("Could not reach the server. Is the backend running?");
  }
  if (!response.ok) throw new Error(await errorMessage(response));

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const feed = createSseParser(onEvent);
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    feed(value);
  }
  feed.end();
}
