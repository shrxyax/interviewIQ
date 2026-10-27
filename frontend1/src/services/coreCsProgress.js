// Which Core CS topics this browser has marked as read. Per-viewer
// convenience only, so it lives in localStorage and degrades to "nothing
// read" when storage is unavailable.

const KEY = "iq_core_cs_read";

export function getReadTopics() {
  try {
    return new Set(JSON.parse(localStorage.getItem(KEY) || "[]"));
  } catch {
    return new Set();
  }
}

export function setTopicRead(noteId, read) {
  const ids = getReadTopics();

  if (read) ids.add(noteId);
  else ids.delete(noteId);

  try {
    localStorage.setItem(KEY, JSON.stringify([...ids]));
  } catch {
    // Storage disabled: progress just won't persist.
  }

  return ids;
}
