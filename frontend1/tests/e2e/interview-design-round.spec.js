// The system-design lab round inside an interview: the brief and the
// starting architecture are shown, the candidate changes replicas on the
// canvas, "Analyze" shows metrics and problems, and submitting sends the
// design and explanation as the answer. Interview endpoints are stubbed
// (no LLM); /auth/register runs for real. The design payload is the real
// URL-shortener prompt (fixtures-design-round.json).

import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

const DESIGN = JSON.parse(readFileSync(new URL("./fixtures-design-round.json", import.meta.url)));
const SESSION_ID = "e2e-design-session";
const CONTEXT_ID = "e2e-design-context";

function payload(state, extra = {}) {
  return {
    session_id: SESSION_ID,
    context_id: CONTEXT_ID,
    state,
    question: "Let's do a hands-on design exercise. Design a URL Shortener.",
    coding: null,
    design: DESIGN,
    question_number: 2,
    questions_asked: 2,
    total_questions: 3,
    time_remaining_seconds: 1500,
    report: null,
    ...extra,
  };
}

const ANALYSIS = {
  summary: { end_to_end_latency_p99_ms: null, max_sustainable_rps: 1600, bottleneck_node: "api" },
  node_metrics: {
    client: { utilisation: 0, saturated: false },
    lb: { utilisation: 0.4, saturated: false },
    api: { utilisation: 12.5, saturated: true },
    cache: { utilisation: 0.4, saturated: false },
    db: { utilisation: 0.6, saturated: false },
  },
  findings: [
    { type: "saturation", node_id: "api", severity: 10, message: "'Shortener API' is saturated (utilisation 1250% of capacity)." },
    { type: "spof", node_id: "db", severity: 6, message: "'URL Mapping DB' has only 1 replica and is a single point of failure." },
  ],
};

async function stub(page) {
  let state = "AI_SPEAKING";
  const sent = { analyses: [], answers: [] };

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
  await page.route(`**/interview/sessions/${SESSION_ID}/design/analyze`, (r) => {
    sent.analyses.push(r.request().postDataJSON().graph);
    return r.fulfill({ json: ANALYSIS });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}/answer`, (r) => {
    sent.answers.push(r.request().postDataJSON().answer);
    state = "AI_SPEAKING";
    return r.fulfill({
      json: payload(state, { question: "How would you handle a cache stampede?", design: null, question_number: 3 }),
    });
  });
  await page.route(`**/interview/sessions/${SESSION_ID}`, (r) => r.fulfill({ json: payload(state) }));
  await page.route(`**/interview/sessions/${SESSION_ID}/proctoring-event`, (r) =>
    r.fulfill({ json: { tab_switch_count: 0, face_lost_count: 0 } })
  );

  return sent;
}

test("design round: read the brief, change the design, analyze, submit", async ({ page }) => {
  const sent = await stub(page);
  await page.setViewportSize({ width: 1440, height: 900 });

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

  // The brief: requirements and per-replica capacities.
  await expect(page.getByRole("heading", { name: "Design a URL Shortener" })).toBeVisible();
  await expect(page.getByText("20,000 requests/s")).toBeVisible();
  await expect(page.locator(".design-catalog")).toContainText("API Service800 req/s");

  // The starting architecture is on the canvas.
  const analyze = page.getByRole("button", { name: "Analyze" });
  await expect(analyze).toBeEnabled({ timeout: 10000 });
  await expect(page.locator(".wb-node")).toHaveCount(5);

  // Scale the API tier.
  await page.locator(".wb-node", { hasText: "Shortener API" }).click();
  await page.getByLabel("Replicas").fill("60");

  await analyze.click();
  await expect(page.getByText("2 problems found")).toBeVisible();
  await expect(page.getByText("1,600 rps")).toBeVisible();
  await expect(page.locator(".wb-node", { hasText: "Shortener API" })).toContainText("SATURATED");
  expect(sent.analyses[0].nodes.find((n) => n.id === "api").params.replicas).toBe(60);

  await page.screenshot({ path: "test-results/design-round.png", fullPage: true });

  await page.getByLabel("Explain your design").fill("Scaled the API to 60 replicas for 20k rps.");
  await page.getByRole("button", { name: "Submit Design" }).click();
  await expect(page.locator(".question-text")).toHaveText("How would you handle a cache stampede?");

  const submitted = JSON.parse(sent.answers[0]);
  expect(submitted.explanation).toBe("Scaled the API to 60 replicas for 20k rps.");
  expect(submitted.graph.nodes.find((n) => n.id === "api").params.replicas).toBe(60);
  expect(submitted.graph.edges).toHaveLength(4);

  await expect(page.getByRole("button", { name: "Submit Design" })).toHaveCount(0);
});
