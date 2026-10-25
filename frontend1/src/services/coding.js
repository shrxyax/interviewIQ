import api from "./api";

export const listProblems = () => api.get("/code/problems").then((r) => r.data);

export const getProblem = (problemId) =>
  api.get(`/code/problems/${problemId}`).then((r) => r.data);

export const runSamples = (problemId, code) =>
  api.post(`/code/problems/${problemId}/run`, { code }).then((r) => r.data);

export const submit = (problemId, code) =>
  api.post(`/code/problems/${problemId}/submit`, { code }).then((r) => r.data);

export const listSubmissions = (problemId) =>
  api.get(`/code/problems/${problemId}/submissions`).then((r) => r.data);
