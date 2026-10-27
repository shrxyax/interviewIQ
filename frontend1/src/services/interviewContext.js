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

// Generous timeout: a coding answer runs every test before the reply.
export const submitInterviewAnswer = (sessionId, answer, emotionSignal = null) =>
  api
    .post(`/interview/sessions/${sessionId}/answer`, { answer, emotion_signal: emotionSignal }, { timeout: 120000 })
    .then((r) => r.data);

// Runs the coding round's visible test cases against `code`.
export const runInterviewCode = (sessionId, code) =>
  api
    .post(`/interview/sessions/${sessionId}/code/run`, { code }, { timeout: 60000 })
    .then((r) => r.data);

// Analyses the design round's draft architecture.
export const analyzeInterviewDesign = (sessionId, graph) =>
  api
    .post(`/interview/sessions/${sessionId}/design/analyze`, { graph }, { timeout: 60000 })
    .then((r) => r.data);

// Ends the interview early; the response is the finished session with its report.
export const endInterviewSession = (sessionId, answer = "", emotionSignal = null) =>
  api
    .post(
      `/interview/sessions/${sessionId}/end`,
      { answer: answer || null, emotion_signal: emotionSignal },
      { timeout: 120000 }
    )
    .then((r) => r.data);

export const reportProctoringEvent = (sessionId, eventType) =>
  api
    .post(`/interview/sessions/${sessionId}/proctoring-event`, { event_type: eventType })
    .then((r) => r.data);

export const getSessionEvidence = (sessionId) =>
  api.get(`/interview/sessions/${sessionId}/evidence`).then((r) => r.data);

// The current question read aloud by the backend, as an audio Blob. The
// unique `t` param stops the browser reusing a clip it cached earlier for
// this URL (the backend keeps its own cache, so this costs nothing).
export const getQuestionAudio = (sessionId) =>
  api
    .get(`/interview/sessions/${sessionId}/question-audio`, {
      params: { t: Date.now() },
      responseType: "blob",
      timeout: 20000,
    })
    .then((r) => r.data);
