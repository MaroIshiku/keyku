import { expect, test } from "@playwright/test";
import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";

const require = createRequire(import.meta.url);
const axePath = require.resolve("axe-core/axe.min.js");
const themes = ["lavender", "mint", "sky", "amber", "rose", "graphite"];
const modes = ["light", "dark"];
const viewports = [{width:390,height:844},{width:412,height:915},{width:768,height:1024},{width:1440,height:900},{width:1920,height:1080}];

async function assertAxe(page, label) {
  const results = await page.evaluate(async () => window.axe.run(document, {runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21aa","wcag22aa"]}}));
  const violations = results.violations.filter((item) => ["critical", "serious"].includes(item.impact));
  expect(violations, `${label}: ${violations.map((item) => `${item.id}: ${item.help}`).join("; ")}`).toEqual([]);
}

async function assertNoHorizontalOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth}));
  expect(dimensions.scrollWidth, `${label} has horizontal overflow`).toBeLessThanOrEqual(dimensions.clientWidth + 1);
}

async function applyTheme(page, theme, mode) {
  await page.evaluate(async ({themeValue,modeValue}) => {
    const controller = await import("/design-system/theme-controller.js");
    controller.setPixelSoftUtilityTheme(themeValue);
    controller.setPixelSoftUtilityMode(modeValue);
  }, {themeValue:theme,modeValue:mode});
  await page.waitForTimeout(350);
}

test("setup, account, vault, sharing, accessibility, themes, and responsive layout", async ({page,context}) => {
  await mkdir(".ishiku/reports/browser/screenshots", {recursive:true});
  await context.addInitScript({path:axePath});
  await page.setViewportSize(viewports[0]);
  await page.goto("/");
  await expect(page.locator("#setup-view")).toBeVisible();
  await assertAxe(page, "first-run setup");
  await page.locator("#setup-secret").fill("synthetic-browser-setup-secret-123456");
  await page.locator('[name="admin_display_name"]').fill("Synthetic Browser Admin");
  await page.locator('[name="admin_username"]').fill("browser-admin");
  await page.locator('[name="admin_password"]').fill("synthetic-browser-admin-password-123456");
  await page.locator('[name="admin_password_confirm"]').fill("synthetic-browser-admin-password-123456");
  await page.locator("#setup-submit").click();
  await expect(page.locator("#app-view")).toBeVisible();
  await expect(page.locator("#rows")).toContainText("No keys yet");

  const me = await page.request.get("/api/auth/me");
  expect(me.ok()).toBeTruthy();
  const csrfToken = me.headers()["x-csrf-token"];
  expect(csrfToken).toBeTruthy();
  const created = await page.request.post("/api/admin/keys", {data:{game:"Synthetic Browser Game",key:"AAAA-BBBB-CCCC"},headers:{"X-CSRF-Token":csrfToken}});
  expect(created.status()).toBe(201);
  await page.reload();
  await expect(page.locator('[data-index="0"]')).toContainText("Synthetic Browser Game");
  await page.locator('[data-index="0"]').click();
  await expect(page.locator("#detail-dialog")).toBeVisible();
  await page.locator("#detail-share").click();
  await expect(page.locator("#detail-share-link")).not.toHaveValue("");
  const shareURL = await page.locator("#detail-share-link").inputValue();
  await assertAxe(page, "key details dialog");
  await page.keyboard.press("Escape");
  await expect(page.locator("#detail-dialog")).toBeHidden();

  for (const theme of themes) for (const mode of modes) {
    await applyTheme(page, theme, mode);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.locator("html")).toHaveAttribute("data-resolved-mode", mode);
    await assertNoHorizontalOverflow(page, `${theme}/${mode}/390x844`);
    await assertAxe(page, `${theme}/${mode}`);
  }

  for (const viewport of viewports) for (const mode of modes) {
    await page.setViewportSize(viewport);
    await applyTheme(page, "amber", mode);
    const label = `amber-${mode}-${viewport.width}x${viewport.height}`;
    await assertNoHorizontalOverflow(page, label);
    await page.screenshot({path:`.ishiku/reports/browser/screenshots/${label}.png`,fullPage:true});
  }

  await page.setViewportSize(viewports[0]);
  await page.locator("#profile-button").click();
  await expect(page.locator("#profile-sheet")).toBeVisible();
  await expect(page.locator("#profile-sheet button").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("#profile-sheet")).toBeHidden();
  await expect(page.locator("#profile-button")).toBeFocused();

  const shared = await context.newPage();
  await shared.setViewportSize(viewports[0]);
  await shared.goto(shareURL);
  await expect(shared.locator("#share-title")).toHaveText("Synthetic Browser Game");
  await shared.waitForTimeout(350);
  await assertAxe(shared, "public share view");
  await shared.close();

  await page.locator("#profile-button").click();
  await page.locator("#logout").click();
  await expect(page.locator("#confirm-dialog")).toBeVisible();
  await page.locator("#confirm-ok").click();
  await expect(page.locator("#auth-view")).toBeVisible();
  await page.locator("#auth-username").fill("browser-admin");
  await page.locator("#auth-password").fill("synthetic-browser-admin-password-123456");
  await page.locator("#auth-submit").click();
  await expect(page.locator("#app-view")).toBeVisible();
  await assertAxe(page, "signed-in vault");
});
