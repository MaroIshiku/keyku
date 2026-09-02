#!/usr/bin/env node

import { createServer } from "node:net";
import { copyFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { spawn, spawnSync } from "node:child_process";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import process from "node:process";

const root = resolve(import.meta.dirname, "..");
const temporary = await mkdtemp(join(tmpdir(), "keyku-browser-"));
const environment = join(temporary, "venv");
const browserRoot = join(temporary, "browser");
let application;

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", ...options });
  if (result.status !== 0) process.exitCode = result.status ?? 1;
  return result.status === 0;
}

async function freePort() {
  return await new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolvePort(address.port));
    });
  });
}

async function waitUntilReady(url) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`${url}/readyz`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolveWait) => setTimeout(resolveWait, 500));
  }
  throw new Error(`Keyku did not become ready at ${url}.`);
}

async function cleanup() {
  if (application && application.exitCode === null) {
    application.kill("SIGTERM");
    await new Promise((resolveWait) => {
      const timer = setTimeout(() => { application.kill("SIGKILL"); resolveWait(); }, 5_000);
      application.once("exit", () => { clearTimeout(timer); resolveWait(); });
    });
  }
  await rm(temporary, { recursive: true, force: true });
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, async () => {
    await cleanup();
    process.exit(128 + (signal === "SIGINT" ? 2 : 15));
  });
}

try {
  await mkdir(join(browserRoot, "tests", "e2e"), { recursive: true });
  await copyFile(join(root, "package.json"), join(browserRoot, "package.json"));
  await copyFile(join(root, "package-lock.json"), join(browserRoot, "package-lock.json"));
  await copyFile(join(root, "playwright.config.mjs"), join(browserRoot, "playwright.config.mjs"));
  await copyFile(join(root, "tests", "e2e", "keyku.spec.mjs"), join(browserRoot, "tests", "e2e", "keyku.spec.mjs"));
  if (!run("npm", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], { cwd: browserRoot })) throw new Error("npm ci failed.");
  const playwright = join(browserRoot, "node_modules", "@playwright", "test", "cli.js");
  if (!run(process.execPath, [playwright, "install", "chromium"], { cwd: browserRoot })) throw new Error("Chromium installation failed.");
  if (!run("python3", ["-m", "venv", environment])) throw new Error("Python virtual environment creation failed.");
  const python = join(environment, "bin", "python");
  if (!run(python, ["-m", "pip", "install", "--disable-pip-version-check", "--requirement", join(root, "python", "requirements.txt")])) throw new Error("Python dependency installation failed.");

  const port = await freePort();
  const baseURL = `http://127.0.0.1:${port}`;
  application = spawn(python, [join(root, "python", "app.py")], {
    cwd: root,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      APP_VERSION: "0.3.3-e2e",
      ISHIKU_APP_URL: baseURL,
      ISHIKU_COOKIE_SECURE: "false",
      ISHIKU_DATA_DIR: join(temporary, "data"),
      ISHIKU_SETUP_SECRET: "synthetic-browser-setup-secret-123456",
      PORT: String(port),
      PUBLIC_DIR: join(root, "public")
    }
  });
  let applicationOutput = "";
  for (const stream of [application.stdout, application.stderr]) stream.on("data", (chunk) => { applicationOutput = `${applicationOutput}${chunk}`.slice(-12_000); });
  application.once("exit", (code) => {
    if (code && process.exitCode == null) { process.stderr.write(applicationOutput); process.exitCode = code; }
  });
  await waitUntilReady(baseURL);
  if (!run(process.execPath, [playwright, "test", "--config", join(browserRoot, "playwright.config.mjs")], {
    env: {
      ...process.env,
      KEYKU_E2E_BASE_URL: baseURL,
      KEYKU_E2E_REPORT_ROOT: join(root, ".ishiku", "reports", "browser")
    }
  })) throw new Error("Browser verification failed.");
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = process.exitCode || 1;
} finally {
  await cleanup();
}
