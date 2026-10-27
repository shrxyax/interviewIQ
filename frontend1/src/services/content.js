import api from "./api";

export const getDsaSheet = () => api.get("/sheets/dsa").then((r) => r.data);

export const setProblemStatus = (problemId, status) =>
  api.post(`/sheets/dsa/problems/${problemId}/status`, { status }).then((r) => r.data);

export const getCoreCs = () => api.get("/sheets/core-cs").then((r) => r.data);

export const getCoreCsTopic = (noteId) =>
  api.get(`/sheets/core-cs/notes/${noteId}`).then((r) => r.data);

export const getCompanies = () => api.get("/companies").then((r) => r.data);

export const getCompanyReadiness = (companyId) =>
  api.get(`/companies/${companyId}/readiness`).then((r) => r.data);

export const getCompanyPlan = (companyId) =>
  api.get(`/companies/${companyId}/plan`).then((r) => r.data);
