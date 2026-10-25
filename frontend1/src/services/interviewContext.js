import api from "./api";

export const createInterviewContext = (body) =>
  api.post("/interview/context", body).then((r) => r.data);

export const getInterviewContext = (contextId) =>
  api.get(`/interview/context/${contextId}`).then((r) => r.data);

export const startInterviewSession = (contextId) =>
  api.post("/interview/sessions", { context_id: contextId }).then((r) => r.data);

export const getInterviewSession = (sessionId) =>
  api.get(`/interview/sessions/${sessionId}`).then((r) => r.data);

export const markListening = (sessionId) =>
  api.post(`/interview/sessions/${sessionId}/listening`).then((r) => r.data);

export const submitInterviewAnswer = (sessionId, answer, emotionSignal = null) =>
  api
    .post(`/interview/sessions/${sessionId}/answer`, { answer, emotion_signal: emotionSignal })
    .then((r) => r.data);

export const reportProctoringEvent = (sessionId, eventType) =>
  api
    .post(`/interview/sessions/${sessionId}/proctoring-event`, { event_type: eventType })
    .then((r) => r.data);

export const getSessionEvidence = (sessionId) =>
  api.get(`/interview/sessions/${sessionId}/evidence`).then((r) => r.data);
