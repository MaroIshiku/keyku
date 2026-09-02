#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const composeFiles = ["docker-compose.yml", "docker-compose.example.yml"];

function compose(args, input) {
  return spawnSync("docker", ["compose", ...args], {
    cwd: root,
    encoding: "utf8",
    input,
    env: {
      ...process.env,
      ISHIKU_SETUP_SECRET: "synthetic-compose-contract-secret-123456",
    },
  });
}

function resolvedCompose(file) {
  const result = compose(["-f", file, "config", "--format", "json"]);
  assert.equal(result.status, 0, `${file} must resolve: ${result.stderr}`);
  return JSON.parse(result.stdout);
}

function validateDocument(document) {
  return compose(["-f", "-", "config", "--quiet"], `${JSON.stringify(document)}\n`);
}

for (const file of composeFiles) {
  const document = resolvedCompose(file);
  const initializer = document.services["keyku-init"];
  const limits = initializer.deploy?.resources?.limits;

  assert(initializer, `${file} must declare keyku-init`);
  assert(limits, `${file} must declare keyku-init deploy limits`);
  assert.equal(Number(initializer.cpus), 0.25, `${file} service CPU limit`);
  assert.equal(Number(limits.cpus), 0.25, `${file} deploy CPU limit`);
  assert.equal(Number(initializer.mem_limit), 33_554_432, `${file} service memory limit`);
  assert.equal(Number(limits.memory), 33_554_432, `${file} deploy memory limit`);
  assert.equal(Number(initializer.pids_limit), 32, `${file} service PID limit`);
  assert.equal(Number(limits.pids), 32, `${file} deploy PID limit`);

  const zimaosNormalized = structuredClone(document);
  zimaosNormalized.services["keyku-init"].deploy.resources.reservations = {
    cpus: "0.00",
    memory: "16777216",
  };
  zimaosNormalized.services["keyku-init"].deploy.placement = {};
  const normalizedResult = validateDocument(zimaosNormalized);
  assert.equal(normalizedResult.status, 0, `${file} must survive ZimaOS-style normalization: ${normalizedResult.stderr}`);

  const originalFailure = structuredClone(document);
  originalFailure.services["keyku-init"].deploy.resources.limits.cpus = "1.00";
  const conflictingResult = validateDocument(originalFailure);
  assert.notEqual(conflictingResult.status, 0, `${file} regression fixture must reproduce the conflicting resource failure`);
}

process.stdout.write("Keyku primary and alternative Compose resource contracts passed.\n");
