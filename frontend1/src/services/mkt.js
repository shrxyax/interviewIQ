import api from "./api";

export const getConceptGraph = (domain = "dsa") =>
  api.get("/concepts/graph", { params: { domain } }).then((r) => r.data);

export const startMktSession = (body) =>
  api.post("/mkt/sessions", body).then((r) => r.data);

export const answerMktTurn = (sessionId, body) =>
  api.post(`/mkt/sessions/${sessionId}/answer`, body).then((r) => r.data);

export const getMktTrace = (sessionId) =>
  api.get(`/mkt/sessions/${sessionId}/trace`).then((r) => r.data);

export const getMktReport = (sessionId) =>
  api.get(`/mkt/sessions/${sessionId}/report`).then((r) => r.data);

export const getProfileBeliefs = (domain = "dsa") =>
  api.get("/profile/beliefs", { params: { domain } }).then((r) => r.data);
