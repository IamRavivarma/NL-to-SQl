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

export const listDocuments = () => request("/api/documents");
export const deleteDocument = (id) => request(`/api/documents/${id}`, { method: "DELETE" });
export const listConversations = () => request("/api/conversations");
export const getConversation = (id) => request(`/api/conversations/${id}`);
export const deleteConversation = (id) => request(`/api/conversations/${id}`, { method: "DELETE" });
export const getStats = () => request("/api/stats");

export function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/upload", { method: "POST", body: form });
}

export function createSseParser(onEvent) {
  let buffer = "";
  return (text) => {
    buffer += text.replace(/\r\n/g, "\n");
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
}
