// Browser-automated proof for the Phase 6 speechSynthesis watchdog fix in
// InterviewScreen.jsx: if neither `onend` nor `onerror` ever fires (a real
// failure mode on some Chrome/Edge builds after tab backgrounding or with
// certain voice-pack states), the UI must still transition AI_SPEAKING ->
// LISTENING within the watchdog's timeout window instead of hanging
// forever. A second test proves the normal (working TTS) happy path still
// reaches LISTENING via the ordinary onend callback, without waiting for
// the watchdog.
//
// The backend's /auth/register runs for real (it's local, fast, and needs
// no LLM key). Upload + interview endpoints are stubbed via page.route so
// the test is deterministic and doesn't depend on an LLM API key being
// configured in this environment. The stub tracks real server-side state
// (AI_SPEAKING -> LISTENING only once /listening is actually called) so a
// test can't pass merely because of the unrelated periodic resync.

import { test, expect } from "@playwright/test";

const SESSION_ID = "e2e-session-1";
const CONTEXT_ID = "e2e-context-1";
const QUESTION = "Tell me about a challenging project you worked on recently.";

function basePayload(state) {
  return {
    session_id: SESSION_ID,
    context_id: CONTEXT_ID,
    state,
    question: QUESTION,
    question_number: 1,
    questions_asked: 1,
    total_questions: 2,
    time_remaining_seconds: 1800,
    report: null,
  };
}

async function stubBackend(page) {
  // Mutable, server-side-like state: only flips to LISTENING once the
  // frontend actually calls POST .../listening, mirroring the real
  // backend's state machine closely enough for this test.
  let state = "READY";

  await page.route("**/upload", (route) =>
    route.fulfill({ json: { resume_id: 1 } })
  );

  await page.route("**/interview/context", (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );

  await page.route(`**/interview/context/${CONTEXT_ID}`, (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );

  await page.route("**/interview/sessions", (route) => {
    if (route.request().method() === "POST") {
      state = "AI_SPEAKING";
      return route.fulfill({ json: basePayload(state) });
    }
    return route.continue();
  });

  await page.route(`**/interview/sessions/${SESSION_ID}/listening`, (route) => {
    state = "LISTENING";
    return route.fulfill({ json: basePayload(state) });
  });

  await page.route(`**/interview/sessions/${SESSION_ID}`, (route) =>
    route.fulfill({ json: basePayload(state) })
  );

  await page.route(`**/interview/sessions/${SESSION_ID}/proctoring-event`, (route) =>
    route.fulfill({ json: { tab_switch_count: 0, face_lost_count: 0 } })
  );
}

async function startInterviewAndReachAiSpeaking(page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("iq_onboarded", "true");
  });

  await stubBackend(page);
  await page.goto("/");

  await page.setInputFiles('input[type="file"]', {
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 fake resume content for e2e test"),
  });

  await page.getByRole("button", { name: /start ai interview on this resume/i }).click();
  await page.getByPlaceholder("Target role (e.g. Frontend Engineer)").fill("Backend Engineer");
  await page.getByRole("button", { name: "Start Interview" }).click();

  // The question is now rendered and the component has moved into
  // AI_SPEAKING, about to call speakQuestion().
  await expect(page.locator(".question-text")).toHaveText(QUESTION);
}

test("silently-dropped speechSynthesis still reaches LISTENING via the watchdog", async ({ page }) => {
  // Simulate the real failure mode: speak() accepts the utterance but
  // never fires onstart, onend or onerror - exactly what some Chrome/Edge
  // builds do after tab backgrounding or a stuck voice pack. cancel() is
  // also a no-op, so the defensive cancel-before-speak() can't rescue it
  // either - only the watchdog timeout can.
  await page.addInitScript(() => {
    window.speechSynthesis.speak = () => {};
    window.speechSynthesis.cancel = () => {};
  });

  const warnings = [];
  page.on("console", (msg) => {
    if (msg.type() === "warning") warnings.push(msg.text());
  });

  await startInterviewAndReachAiSpeaking(page);

  const start = Date.now();

  // canAnswer (and therefore the voice-answer / submit controls) only
  // becomes true once the backend session is LISTENING, which only
  // happens once onReadyForAnswer() fires - i.e. once the watchdog (or a
  // real onend/onerror) resolves speakQuestion(). Bound this well under
  // the hard SPEECH_WATCHDOG_MAX_MS ceiling (45s) so a regression that
  // makes the component hang forever is a real, visible test failure
  // rather than a 60s timeout with no diagnosis.
  await expect(page.getByPlaceholder(/click start answer and speak/i)).toBeEnabled({
    timeout: 50000,
  });

  const elapsedMs = Date.now() - start;

  // The question is ~70 chars, so the watchdog's own estimate puts it at
  // ~9s; this lower bound just proves we didn't resolve near-instantly
  // through some unrelated path (e.g. the periodic resync).
  expect(elapsedMs).toBeGreaterThan(6000);
  expect(warnings.some((w) => w.includes("speechSynthesis watchdog fired"))).toBe(true);
});

test("normal speechSynthesis (onend fires) reaches LISTENING without waiting for the watchdog", async ({ page }) => {
  await page.addInitScript(() => {
    window.speechSynthesis.speak = (utterance) => {
      if (typeof utterance.onstart === "function") utterance.onstart();
      setTimeout(() => {
        if (typeof utterance.onend === "function") utterance.onend();
      }, 300);
    };
  });

  const warnings = [];
  page.on("console", (msg) => {
    if (msg.type() === "warning") warnings.push(msg.text());
  });

  await startInterviewAndReachAiSpeaking(page);

  const start = Date.now();

  await expect(page.getByPlaceholder(/click start answer and speak/i)).toBeEnabled({
    timeout: 8000,
  });

  const elapsedMs = Date.now() - start;

  // Proves the ordinary onend path resolved this, not the ~9s watchdog.
  expect(elapsedMs).toBeLessThan(6000);
  expect(warnings.some((w) => w.includes("speechSynthesis watchdog fired"))).toBe(false);
});
