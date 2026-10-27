// Regression test: "Start Answer" must keep listening until the candidate
// presses "Stop Answer". Browsers end a SpeechRecognition run on their own
// after a pause or ~60s; the UI must restart it transparently and keep the
// words already transcribed, instead of flipping back to "Start Answer".
//
// SpeechRecognition is replaced with a fake the test drives directly, and the
// interview endpoints are stubbed so no backend or LLM key is needed.

import { test, expect } from "@playwright/test";

const SESSION_ID = "e2e-speech-session";
const CONTEXT_ID = "e2e-speech-context";
const QUESTION = "How would you cache a leaderboard?";

async function openListeningInterview(page) {
  await page.addInitScript((sessionId) => {
    window.localStorage.setItem("iq_onboarded", "true");
    window.localStorage.setItem("iq_active_interview_session_id", sessionId);

    class FakeRecognition {
      constructor() {
        this.running = false;
        this.starts = 0;
        window.__recognition = this;
      }

      start() {
        if (this.running) throw new Error("already started");
        this.running = true;
        this.starts += 1;
        setTimeout(() => this.onstart?.(), 0);
      }

      stop() {
        if (!this.running) return;
        this.running = false;
        setTimeout(() => this.onend?.(), 0);
      }

      // Test helpers
      say(text) {
        const result = [{ transcript: text }];
        result.isFinal = true;
        this.onresult({ resultIndex: 0, results: [result] });
      }

      browserEndsOnItsOwn() {
        this.running = false;
        if (this.onerror) this.onerror({ error: "no-speech" });
        if (this.onend) this.onend();
      }
    }

    window.SpeechRecognition = FakeRecognition;
    window.webkitSpeechRecognition = FakeRecognition;
  }, SESSION_ID);

  await page.route("**/interview/context/**", (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );

  await page.route("**/interview/sessions/**", (route) =>
    route.fulfill({
      json: {
        session_id: SESSION_ID,
        context_id: CONTEXT_ID,
        state: "LISTENING",
        question: QUESTION,
        question_number: 1,
        questions_asked: 1,
        total_questions: 2,
        time_remaining_seconds: 1800,
        report: null,
      },
    })
  );

  await page.goto("/");
  // App start signs in against the real local backend first, which can be
  // slow while other e2e tests hit it in parallel.
  await expect(page.locator(".question-text")).toHaveText(QUESTION, { timeout: 15000 });
}

test("listening survives the browser ending recognition, until Stop is pressed", async ({ page }) => {
  await openListeningInterview(page);

  const answerBox = page.locator(".answer-section textarea");

  await page.getByRole("button", { name: "Start Answer" }).click();
  await expect(page.getByRole("button", { name: "Stop Answer" })).toBeVisible();

  await page.evaluate(() => window.__recognition.say("I would use Redis"));
  await expect(answerBox).toHaveValue("I would use Redis");

  // The browser stops by itself after a pause: we must still be listening,
  // having restarted recognition, with the earlier words kept.
  await page.evaluate(() => window.__recognition.browserEndsOnItsOwn());
  await expect(page.getByRole("button", { name: "Stop Answer" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__recognition.starts)).toBe(2);
  await expect(answerBox).toHaveValue("I would use Redis");

  await page.evaluate(() => window.__recognition.say("with a short TTL"));
  await expect(answerBox).toHaveValue("I would use Redis with a short TTL");

  // Only the candidate's Stop actually ends listening.
  await page.getByRole("button", { name: "Stop Answer" }).click();
  await expect(page.getByRole("button", { name: "Start Answer" })).toBeVisible();
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.__recognition.starts)).toBe(2);
  expect(await page.evaluate(() => window.__recognition.running)).toBe(false);
});
