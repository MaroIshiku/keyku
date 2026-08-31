import { defineConfig } from "@playwright/test";

const reportRoot = process.env.KEYKU_E2E_REPORT_ROOT || ".ishiku/reports/browser";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  timeout: 300_000,
  expect: { timeout: 10_000 },
  outputDir: `${reportRoot}/artifacts`,
  reporter: [["line"], ["json", { outputFile: `${reportRoot}/playwright.json` }]],
  use: {
    baseURL: process.env.KEYKU_E2E_BASE_URL,
    browserName: "chromium",
    headless: true,
    locale: "en-US",
    timezoneId: "Europe/Berlin",
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  }
});
