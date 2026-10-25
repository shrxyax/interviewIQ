import api from "./api";

const TOKEN_KEY = "iq_token";
const USERNAME_KEY = "iq_username";

/**
 * Transparent per-browser identity: on first visit we silently register
 * a random account so progress (sheet status, MKT beliefs, sessions)
 * persists for this browser without a login screen getting in the way
 * of a judge trying the demo. A real login/register screen (below) lets
 * someone carry their progress to another device if they want to.
 */
export async function ensureIdentity() {
  const existing = localStorage.getItem(TOKEN_KEY);
  if (existing) return;

  const username = `guest_${Math.random().toString(36).slice(2, 10)}`;
  const password = Math.random().toString(36).slice(2, 14);

  const res = await api.post("/auth/register", { username, password });
  localStorage.setItem(TOKEN_KEY, res.data.access_token);
  localStorage.setItem(USERNAME_KEY, res.data.username);
  // Stash the generated password locally only so the user can see/copy
  // it if they want to log in elsewhere; never sent anywhere else.
  localStorage.setItem("iq_generated_password", password);
}

export function getUsername() {
  return localStorage.getItem(USERNAME_KEY) || "Guest";
}

export function getGeneratedPassword() {
  return localStorage.getItem("iq_generated_password") || "";
}

export async function login(username, password) {
  const res = await api.post("/auth/login", { username, password });
  localStorage.setItem(TOKEN_KEY, res.data.access_token);
  localStorage.setItem(USERNAME_KEY, res.data.username);
  localStorage.removeItem("iq_generated_password");
}

export async function register(username, password) {
  const res = await api.post("/auth/register", { username, password });
  localStorage.setItem(TOKEN_KEY, res.data.access_token);
  localStorage.setItem(USERNAME_KEY, res.data.username);
  localStorage.removeItem("iq_generated_password");
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  localStorage.removeItem("iq_generated_password");
}

export function isTransientGuest() {
  return !!getGeneratedPassword();
}
