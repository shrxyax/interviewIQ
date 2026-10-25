import api from "./api";

export const startAttempt = () => api.post("/aptitude/attempts").then((r) => r.data);

export const getAttempt = (attemptId) =>
  api.get(`/aptitude/attempts/${attemptId}`).then((r) => r.data);

export const submitAttempt = (attemptId, answers) =>
  api.post(`/aptitude/attempts/${attemptId}/submit`, { answers }).then((r) => r.data);

export const listAttempts = () => api.get("/aptitude/attempts").then((r) => r.data);
