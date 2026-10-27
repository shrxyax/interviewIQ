// The live coding round inside an interview: the problem and its visible
// tests are shown, code is written in the editor, "Run tests" shows each
// test's input/expected/output/error and how many pass, and submitting
// sends the code as the answer. Interview endpoints are stubbed (no LLM);
// /auth/register runs for real.

import { test, expect } from "@playwright/test";

const SESSION_ID = "e2e-coding-session";
const CONTEXT_ID = "e2e-coding-context";
const STARTER = "def solve(nums, target):\n    # return [i, j]\n    pass\n";
const SOLUTION =
  "def solve(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target - n], i]\n        seen[n] = i\n";

const CODING = {
  language: "python",
  code: STARTER,
  problem: {
    id: "code.two_sum",
    title: "Two Sum",
    difficulty: "Easy",
    statement: "Return the indices of the two numbers that add up to `target`.",
    signature: "def solve(nums, target):",
    starter_code: STARTER,
    tests: [
      { args: [[2, 7, 11, 15], 9], expected: [0, 1] },
      { args: [[3, 2, 4], 6], expected: [1, 2] },
    ],
    hidden_test_count: 2,
  },
};

function payload(state, extra = {}) {
  return {
    session_id: SESSION_ID,
    context_id: CONTEXT_ID,
    state,
    question: "Let's move to a coding round. Please solve Two Sum.",
    coding: CODING,
    question_number: 2,
    questions_asked: 2,
    total_questions: 3,
    time_remaining_seconds: 1500,
    report: null,
    ...extra,
  };
}

async function stub(page) {
  let state = "AI_SPEAKING";
  const sent = { runs: [], answers: [] };

  await page.route("**/question-audio*", (r) => r.fulfill({ status: 503, json: { detail: "unavailable" } }));
  await page.route("**/upload", (r) => r.fulfill({ json: { resume_id: 1 } }));
  await page.route("**/interview/context", (r) => r.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } }));
  await page.route(`**/interview/context/${CONTEXT_ID}`, (r) =>
    r.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );
  await page.route("**/interview/sessions", (r) => r.fulfill({ json: payload(state) }));
  await page.route(`**/interview/sessions/${SESSION_ID}/listening`, (r) => {
    state = "LISTENING";
    return r.fulfill({ json: payload(state) });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}/code/run`, (r) => {
    sent.runs.push(r.request().postDataJSON().code);
    return r.fulfill({
      json: {
        passed: 1,
        total: 2,
        results: [
          { status: "ok", output: [0, 1], error: null, runtime_ms: 31, args: [[2, 7, 11, 15], 9], expected: [0, 1] },
          {
            status: "runtime_error",
            output: null,
            error: "name 'seen' is not defined",
            runtime_ms: 28,
            args: [[3, 2, 4], 6],
            expected: [1, 2],
          },
        ],
      },
    });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}/answer`, (r) => {
    sent.answers.push(r.request().postDataJSON().answer);
    state = "AI_SPEAKING";
    return r.fulfill({
      json: payload(state, { question: "How would you handle duplicates?", coding: null, question_number: 3 }),
    });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}`, (r) => r.fulfill({ json: payload(state) }));
  await page.route(`**/interview/sessions/${SESSION_ID}/proctoring-event`, (r) =>
    r.fulfill({ json: { tab_switch_count: 0, face_lost_count: 0 } })
  );

  return sent;
}

test("coding round: see the problem, run tests, read results, submit the code", async ({ page }) => {
  const sent = await stub(page);

  await page.addInitScript(() => {
    window.localStorage.setItem("iq_onboarded", "true");
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

  // The problem, its signature and visible tests.
  await expect(page.getByRole("heading", { name: "Two Sum" })).toBeVisible();
  await expect(page.getByText("nums = [2,7,11,15], target = 9")).toBeVisible();
  await expect(page.getByText("+ 2 hidden tests, checked when you submit.")).toBeVisible();

  // The editor holds the starter code once the room is listening.
  const runButton = page.getByRole("button", { name: "Run tests" });
  await expect(runButton).toBeEnabled({ timeout: 10000 });
  await expect(page.locator(".monaco-editor")).toBeVisible({ timeout: 20000 });

  // Typing goes through Monaco's auto-indent; set the text directly instead,
  // which fires the same change event the component listens to.
  await expect(page.locator(".monaco-editor")).toContainText("return [i, j]");
  await page.evaluate((text) => window.monaco.editor.getModels()[0].setValue(text), SOLUTION);

  await runButton.click();
  await expect(page.getByText("1/2 tests passing")).toBeVisible();
  await expect(page.getByText("Test 1: Passed")).toBeVisible();
  await expect(page.getByText("Test 2: Error")).toBeVisible();
  await expect(page.getByText("name 'seen' is not defined")).toBeVisible();
  expect(sent.runs[0]).toBe(SOLUTION);

  await page.screenshot({ path: "test-results/coding-round.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: "test-results/coding-round-1440.png", fullPage: true });

  await page.getByRole("button", { name: "Submit Solution" }).click();
  await expect(page.locator(".question-text")).toHaveText("How would you handle duplicates?");
  expect(sent.answers).toEqual([SOLUTION.trim()]);

  // Back to a spoken question: the normal answer box returns.
  await expect(page.getByRole("button", { name: "Run tests" })).toHaveCount(0);
});
