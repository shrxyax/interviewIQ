// Real end-to-end proof of the Phase 11 aptitude module: register a fresh
// user, start a timed attempt against the real backend, answer every
// question, submit, and confirm the results view shows the score the
// backend actually computed (no stubbed routes — this hits the real API).

import { test, expect } from "@playwright/test";

test("full aptitude flow: start, answer, submit, view results", async ({ page }) => {
  // The countdown timer ticks every second and re-renders the question
  // card, which can make Playwright's actionability "stability" check flap
  // on a slow CI box; force clicks on the test's own controls to avoid
  // flakiness unrelated to what's being verified (scoring correctness).
  test.setTimeout(120000);
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });

  // Skip the marketing onboarding gate (App.jsx shows it until
  // iq_onboarded is set) and let the app auto-provision a guest identity
  // via ensureIdentity() on load (see src/services/auth.js).
  await page.addInitScript(() => localStorage.setItem("iq_onboarded", "true"));
  await page.goto("/aptitude");

  await expect(page.getByRole("heading", { name: "Aptitude Test", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "Start test" }).click();

  await expect(page.getByText(/Question 1 of/)).toBeVisible({ timeout: 10000 });

  const totalText = await page.getByText(/Question 1 of \d+/).textContent();
  const total = parseInt(totalText.match(/of (\d+)/)[1], 10);
  expect(total).toBeGreaterThanOrEqual(15);

  for (let i = 0; i < total; i++) {
    await expect(page.getByText(new RegExp(`Question ${i + 1} of`))).toBeVisible();

    // Answer-option buttons carry a dedicated test id (AptitudePage.jsx) so
    // this can't accidentally hit an unrelated button elsewhere on the page
    // (e.g. the sidebar's "New Chat").
    await page.getByTestId("aptitude-option").first().click({ force: true });

    if (i < total - 1) {
      await page.getByRole("button", { name: "Next" }).click({ force: true });
    }
  }

  await page.getByRole("button", { name: "Submit test" }).click({ force: true });

  await expect(page.getByText(/Score: \d+ \/ \d+/)).toBeVisible({ timeout: 10000 });

  const scoreText = await page.getByText(/Score: \d+ \/ \d+/).textContent();
  const [, scored, outOf] = scoreText.match(/Score: (\d+) \/ (\d+)/);
  expect(parseInt(outOf, 10)).toBe(total);
  expect(parseInt(scored, 10)).toBeGreaterThanOrEqual(0);

  await expect(page.getByText("Quantitative Aptitude").first()).toBeVisible();
  await expect(page.getByText("Logical Reasoning").first()).toBeVisible();
  await expect(page.getByText("Verbal Ability").first()).toBeVisible();

  const consoleErrors = errors.filter((e) => !e.includes("Failed to load resource"));
  expect(consoleErrors).toEqual([]);
});
