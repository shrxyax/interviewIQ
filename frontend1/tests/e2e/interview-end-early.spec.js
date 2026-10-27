// Ending an interview before the time runs out must still show the report
// for what was answered, including an answer that was typed but not yet
// submitted. Interview endpoints are stubbed (as in the other interview
// specs) so no LLM is needed; /auth/register runs for real.

import { test, expect } from "@playwright/test";

const SESSION_ID = "e2e-end-session";
const CONTEXT_ID = "e2e-end-context";
const QUESTION = "What is the difference between a process and a thread?";
const TYPED = "A process has its own memory while threads share it.";

const REPORT = {
  overall_score: 64,
  communication: 70,
  technical_knowledge: 60,
  answer_relevance: 72,
  clarity: 66,
  problem_solving: 58,
  strengths: ["Stays focused on what was asked."],
  areas_for_improvement: ["Support answers with concrete examples from your projects."],
  final_feedback: "You answered 1 question.",
  ended_early: true,
  question_feedback: [
    { question: QUESTION, answer: TYPED, score: 6, evaluation: "What worked: Stays focused on what was asked." },
  ],
};

function payload(state) {
  return {
    session_id: SESSION_ID,
    context_id: CONTEXT_ID,
    state,
    question: state === "REPORT" ? null : QUESTION,
    question_number: 1,
    questions_asked: 1,
    total_questions: 5,
    time_remaining_seconds: 1800,
    report: state === "REPORT" ? REPORT : null,
  };
}

async function stubBackend(page, { endFails = false } = {}) {
  let state = "READY";
  const endBodies = [];

  await page.route("**/question-audio*", (route) => route.fulfill({ status: 503, json: { detail: "unavailable" } }));
  await page.route("**/upload", (route) => route.fulfill({ json: { resume_id: 1 } }));
  await page.route("**/interview/context", (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );
  await page.route(`**/interview/context/${CONTEXT_ID}`, (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );
  await page.route("**/interview/sessions", (route) => {
    state = "AI_SPEAKING";
    return route.fulfill({ json: payload(state) });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}/listening`, (route) => {
    state = "LISTENING";
    return route.fulfill({ json: payload(state) });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}/end`, (route) => {
    endBodies.push(route.request().postDataJSON());
    if (endFails) return route.fulfill({ status: 500, json: { detail: "Report generation failed." } });
    state = "REPORT";
    return route.fulfill({ json: payload(state) });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}`, (route) => route.fulfill({ json: payload(state) }));
  await page.route(`**/interview/sessions/${SESSION_ID}/proctoring-event`, (route) =>
    route.fulfill({ json: { tab_switch_count: 0, face_lost_count: 0 } })
  );
  await page.route(`**/interview/sessions/${SESSION_ID}/evidence`, (route) =>
    route.fulfill({ json: { session_id: SESSION_ID, item_count: 0, items: [] } })
  );

  return endBodies;
}

async function reachListeningAndType(page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("iq_onboarded", "true");
    // Speech "finishes" quickly so the room moves on to LISTENING.
    window.speechSynthesis.speak = (u) => {
      u.onstart?.();
      setTimeout(() => u.onend?.(), 200);
    };
  });

  await page.goto("/");
  await page.setInputFiles('input[type="file"]', {
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 fake resume content for e2e test"),
  });
  await page.getByRole("button", { name: /start ai interview on this resume/i }).click();
  await page.getByPlaceholder("Target role (e.g. Frontend Engineer)").fill("Backend Engineer");
  await page.getByRole("button", { name: "Start Interview" }).click();

  const box = page.getByPlaceholder(/click start answer and speak/i);
  await expect(box).toBeEnabled({ timeout: 10000 });
  await box.fill(TYPED);
}

test("ending early shows the report and includes the unsubmitted answer", async ({ page }) => {
  const endBodies = await stubBackend(page);
  await reachListeningAndType(page);

  await page.getByRole("button", { name: "End Interview" }).click();
  const dialog = page.getByRole("dialog", { name: "End the interview now?" });
  await expect(dialog).toContainText("including the answer you are typing");

  // "Keep going" leaves the interview untouched.
  await dialog.getByRole("button", { name: "Keep going" }).click();
  await expect(dialog).toBeHidden();
  expect(endBodies).toHaveLength(0);

  await page.getByRole("button", { name: "End Interview" }).click();
  await dialog.getByRole("button", { name: "End and see report" }).click();

  await expect(page.getByRole("heading", { name: "Final Interview Report" })).toBeVisible();
  await expect(page.getByText(TYPED)).toBeVisible();
  expect(endBodies).toHaveLength(1);
  expect(endBodies[0].answer).toBe(TYPED);
});

test("if ending fails the candidate stays in the interview and sees why", async ({ page }) => {
  await stubBackend(page, { endFails: true });
  await reachListeningAndType(page);

  await page.getByRole("button", { name: "End Interview" }).click();
  const dialog = page.getByRole("dialog", { name: "End the interview now?" });
  await dialog.getByRole("button", { name: "End and see report" }).click();

  await expect(dialog.getByRole("alert")).toHaveText("Report generation failed.");
  await dialog.getByRole("button", { name: "Keep going" }).click();
  await expect(page.locator(".question-text")).toHaveText(QUESTION);
  await expect(page.getByPlaceholder(/click start answer and speak/i)).toHaveValue(TYPED);
});
