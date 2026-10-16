export function chunkLabel(count) {
  return `${count} ${count === 1 ? "chunk" : "chunks"}`;
}

export function formatSeconds(ms) {
  return ms == null ? "—" : `${(ms / 1000).toFixed(2)} s`;
}

export function tabFromHash(hash) {
  return hash === "#dashboard" ? "dashboard" : "chat";
}
