import api from "./api";

export const getCatalog = () => api.get("/design/catalog").then((r) => r.data);
export const getScenarioCatalog = () => api.get("/design/scenario-catalog").then((r) => r.data);
export const getSubtopics = () => api.get("/design/subtopics").then((r) => r.data);

export const getPrompts = (params = {}) =>
  api.get("/design/prompts", { params }).then((r) => r.data);

export const startDesignSession = (promptId) =>
  api.post("/design/sessions", { prompt_id: promptId }).then((r) => r.data);

export const saveVersion = (sessionId, graph) =>
  api.post(`/design/sessions/${sessionId}/versions`, { graph }).then((r) => r.data);

export const analyzeVersion = (versionId, body = {}) =>
  api.post(`/design/versions/${versionId}/analyze`, body).then((r) => r.data);

export const simulateVersion = (versionId, body = {}) =>
  api.post(`/design/versions/${versionId}/simulate`, body).then((r) => r.data);

export const runResilience = (versionId) =>
  api.post(`/design/versions/${versionId}/resilience`).then((r) => r.data);

export const interviewerNext = (sessionId) =>
  api.post(`/design/sessions/${sessionId}/interviewer/next`).then((r) => r.data);

export const respond = (sessionId, text) =>
  api.post(`/design/sessions/${sessionId}/respond`, { text }).then((r) => r.data);

export const getDialogue = (sessionId) =>
  api.get(`/design/sessions/${sessionId}/dialogue`).then((r) => r.data);

export const getDesignReport = (sessionId) =>
  api.get(`/design/sessions/${sessionId}/report`).then((r) => r.data);
