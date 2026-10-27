// Regression test: the interviewer's question must actually be read aloud.
//
// In development React StrictMode mounts the interview room, unmounts it and
// mounts it again. The unmount used to cancel speech, and the remount skipped
// speaking because it believed the question had already been read, so the
// candidate heard nothing. The cancelled utterance's late `onerror` could also
// mark the question as "done" and jump straight to LISTENING.
//
// The question is normally read from audio rendered by the backend, with the
// browser's speechSynthesis as the fallback. These tests cover both paths:
// the fallback (backend audio unavailable) with speechSynthesis replaced by a
// recorder, and the backend-audio path with a real WAV file. Interview
// endpoints are stubbed so no LLM key is needed.

import { test, expect } from "@playwright/test";

const SESSION_ID = "e2e-tts-session";
const CONTEXT_ID = "e2e-tts-context";
const QUESTION = "Tell me about a system you designed end to end.";

// A short, valid, silent WAV (0.4s, 8kHz mono 16-bit).
function silentWav(seconds = 0.4, rate = 8000) {
  const samples = Math.round(seconds * rate);
  const data = Buffer.alloc(samples * 2);
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  return Buffer.concat([header, data]);
}

test("browser fallback: the question is spoken and stays spoken until it finishes", async ({ page }) => {
  let listeningCalls = 0;

  await page.addInitScript((sessionId) => {
    window.localStorage.setItem("iq_onboarded", "true");
    window.localStorage.setItem("iq_active_interview_session_id", sessionId);

    const tts = { log: [], current: null };
    window.__tts = tts;

    const synth = {
      speaking: false,
      pending: false,
      paused: false,
      onvoiceschanged: null,
      // Empty, as in Chrome before its voice list has loaded.
      getVoices() {
        return [];
      },
      addEventListener() {},
      removeEventListener() {},
      speak(utterance) {
        tts.log.push(`speak:${utterance.text}`);
        tts.current = utterance;
        this.speaking = true;
        setTimeout(() => utterance.onstart?.(), 10);
      },
      cancel() {
        tts.log.push("cancel");
        const utterance = tts.current;
        tts.current = null;
        this.speaking = false;
        // Like Chrome: a cancelled utterance reports an error asynchronously.
        if (utterance) setTimeout(() => utterance.onerror?.({ error: "interrupted" }), 0);
      },
      pause() {},
      resume() {},
    };

    tts.finish = () => {
      const utterance = tts.current;
      tts.current = null;
      synth.speaking = false;
      utterance?.onend?.();
    };

    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
  }, SESSION_ID);

  const payload = (state) => ({
    session_id: SESSION_ID,
    context_id: CONTEXT_ID,
    state,
    question: QUESTION,
    question_number: 1,
    questions_asked: 1,
    total_questions: 2,
    time_remaining_seconds: 1800,
    report: null,
  });

  await page.route("**/interview/context/**", (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );

  await page.route("**/interview/sessions/**", (route) => {
    if (route.request().url().includes("/question-audio")) {
      return route.fulfill({ status: 503, json: { detail: "unavailable" } });
    }
    if (route.request().url().endsWith("/listening")) {
      listeningCalls += 1;
      return route.fulfill({ json: payload("LISTENING") });
    }
    return route.fulfill({ json: payload("AI_SPEAKING") });
  });

  await page.goto("/");
  // App start signs in against the real local backend first.
  await expect(page.locator(".question-text")).toHaveText(QUESTION, { timeout: 15000 });

  // Give any mount/unmount/remount churn time to settle.
  await page.waitForTimeout(800);

  // The question is being spoken right now, and nothing has skipped ahead.
  expect(await page.evaluate(() => window.__tts.current?.text ?? null)).toBe(QUESTION);
  expect(listeningCalls).toBe(0);
  await expect(page.locator(".ai-avatar-status")).toHaveText(/speaking/i);

  // When the speech really finishes, the interview moves on to the answer.
  await page.evaluate(() => window.__tts.finish());
  await expect.poll(() => listeningCalls).toBe(1);

  // "Replay question" reads it again without re-triggering the handover.
  await page.getByRole("button", { name: "Replay question" }).click();
  await expect.poll(() => page.evaluate(() => window.__tts.current?.text ?? null)).toBe(QUESTION);
  await page.evaluate(() => window.__tts.finish());
  await page.waitForTimeout(300);
  expect(listeningCalls).toBe(1);
});

test("browser fallback: a blocked voice is explained and can be replayed with a click", async ({ page }) => {
  await page.addInitScript((sessionId) => {
    window.localStorage.setItem("iq_onboarded", "true");
    window.localStorage.setItem("iq_active_interview_session_id", sessionId);

    const tts = { blocked: true, spoken: [] };
    window.__tts = tts;

    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: {
        speaking: false,
        pending: false,
        getVoices: () => [],
        addEventListener() {},
        removeEventListener() {},
        cancel() {},
        pause() {},
        resume() {},
        speak(utterance) {
          if (tts.blocked) {
            // What Chrome does without a user gesture.
            setTimeout(() => utterance.onerror?.({ error: "not-allowed" }), 0);
            return;
          }
          tts.spoken.push(utterance.text);
          setTimeout(() => utterance.onstart?.(), 0);
        },
      },
    });
  }, SESSION_ID);

  await page.route("**/interview/context/**", (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );
  await page.route("**/interview/sessions/**", (route) =>
    route.request().url().includes("/question-audio")
      ? route.fulfill({ status: 503, json: { detail: "unavailable" } })
      : route.fulfill({
      json: {
        session_id: SESSION_ID,
        context_id: CONTEXT_ID,
        state: route.request().url().endsWith("/listening") ? "LISTENING" : "AI_SPEAKING",
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
  await expect(page.locator(".question-text")).toHaveText(QUESTION, { timeout: 15000 });
  await expect(page.locator(".speech-issue")).toContainText("blocked");

  await page.evaluate(() => { window.__tts.blocked = false; });
  await page.getByRole("button", { name: "Replay question" }).click();
  await expect.poll(() => page.evaluate(() => window.__tts.spoken)).toContain(QUESTION);
  await expect(page.locator(".speech-issue")).toHaveCount(0);
});

test("backend audio: the question plays as audio, then hands over to the candidate", async ({ page }) => {
  let listeningCalls = 0;
  let audioRequests = 0;

  await page.addInitScript((sessionId) => {
    window.localStorage.setItem("iq_onboarded", "true");
    window.localStorage.setItem("iq_active_interview_session_id", sessionId);

    // Browser speech must not be needed when backend audio works.
    window.__browserSpeech = 0;
    const synth = window.speechSynthesis;
    const speak = synth.speak.bind(synth);
    synth.speak = (u) => {
      window.__browserSpeech += 1;
      speak(u);
    };
  }, SESSION_ID);

  await page.route("**/interview/context/**", (route) =>
    route.fulfill({ json: { context_id: CONTEXT_ID, target_role: "Backend Engineer" } })
  );

  await page.route("**/interview/sessions/**", (route) => {
    const url = route.request().url();

    if (url.includes("/question-audio")) {
      audioRequests += 1;
      return route.fulfill({ status: 200, contentType: "audio/wav", body: silentWav() });
    }

    const state = url.endsWith("/listening") ? "LISTENING" : "AI_SPEAKING";
    if (state === "LISTENING") listeningCalls += 1;

    return route.fulfill({
      json: {
        session_id: SESSION_ID,
        context_id: CONTEXT_ID,
        state,
        question: QUESTION,
        question_number: 1,
        questions_asked: 1,
        total_questions: 2,
        time_remaining_seconds: 1800,
        report: null,
      },
    });
  });

  await page.goto("/");
  await expect(page.locator(".question-text")).toHaveText(QUESTION, { timeout: 15000 });

  // The clip plays to the end, and only then does the interview move on.
  await expect.poll(() => listeningCalls, { timeout: 10000 }).toBe(1);
  expect(audioRequests).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__browserSpeech)).toBe(0);
});
