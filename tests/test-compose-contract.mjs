#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const composeFiles = ["docker-compose.yml", "docker-compose.example.yml"];
const contractImage = process.env.KEYKU_CONTRACT_IMAGE ?? "keyku:verify";

function docker(args) {
  return spawnSync("docker", args, {
    cwd: root,
    encoding: "utf8",
  });
}

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

function validateMemoryContract(limit, reservation) {
  if (limit < reservation) {
    throw new RangeError("Minimum memory limit can not be less than memory reservation limit");
  }
}

assert.doesNotThrow(() => validateMemoryContract(268_435_456, 256_000_000));
assert.throws(
  () => validateMemoryContract(134_217_728, 256_000_000),
  /minimum memory limit can not be less than memory reservation limit/i,
);

for (const file of composeFiles) {
  const document = resolvedCompose(file);
  const expectedServices = {
    "keyku-init": { cpus: 0.25, memory: 268_435_456, pids: 32 },
    keyku: { cpus: 0.5, memory: 268_435_456, pids: 128 },
  };

  for (const [serviceName, expected] of Object.entries(expectedServices)) {
    const service = document.services[serviceName];
    const limits = service?.deploy?.resources?.limits;

    assert(service, `${file} must declare ${serviceName}`);
    assert(limits, `${file} must declare ${serviceName} deploy limits`);
    assert.equal(Number(service.cpus), expected.cpus, `${file} ${serviceName} service CPU limit`);
    assert.equal(Number(limits.cpus), expected.cpus, `${file} ${serviceName} deploy CPU limit`);
    assert.equal(Number(service.mem_limit), expected.memory, `${file} ${serviceName} service memory limit`);
    assert.equal(Number(limits.memory), expected.memory, `${file} ${serviceName} deploy memory limit`);
    assert.equal(Number(service.pids_limit), expected.pids, `${file} ${serviceName} service PID limit`);
    assert.equal(Number(limits.pids), expected.pids, `${file} ${serviceName} deploy PID limit`);
  }

  const zimaosNormalized = structuredClone(document);
  for (const service of Object.values(zimaosNormalized.services)) {
    service.deploy.resources.reservations = {
      cpus: "0.00",
      memory: "256MB",
    };
    service.deploy.placement = {};
  }
  const normalizedResult = validateDocument(zimaosNormalized);
  assert.equal(normalizedResult.status, 0, `${file} must survive ZimaOS-style normalization: ${normalizedResult.stderr}`);

  const originalFailure = structuredClone(document);
  originalFailure.services["keyku-init"].deploy.resources.limits.cpus = "1.00";
  const conflictingResult = validateDocument(originalFailure);
  assert.notEqual(conflictingResult.status, 0, `${file} regression fixture must reproduce the conflicting resource failure`);

}

const imageResult = docker(["image", "inspect", contractImage]);
assert.equal(imageResult.status, 0, `${contractImage} must exist before the daemon resource contract runs: ${imageResult.stderr}`);

const successfulContainer = `keyku-memory-contract-ok-${process.pid}`;
try {
  const successfulResult = docker([
    "create",
    "--name",
    successfulContainer,
    "--memory",
    "268435456",
    "--memory-reservation",
    "256000000",
    contractImage,
    "true",
  ]);
  assert.equal(successfulResult.status, 0, `Docker must accept Keyku's ZimaOS memory contract: ${successfulResult.stderr}`);
} finally {
  docker(["rm", "--force", successfulContainer]);
}

const failingContainer = `keyku-memory-contract-regression-${process.pid}`;
try {
  const failingResult = docker([
    "create",
    "--name",
    failingContainer,
    "--memory",
    "134217728",
    "--memory-reservation",
    "256000000",
    contractImage,
    "true",
  ]);
  if (failingResult.status === 0) {
    const inspectResult = docker(["inspect", failingContainer, "--format", "{{json .HostConfig}}"]);
    assert.equal(inspectResult.status, 0, `The Docker-compatible runtime must expose the regression fixture: ${inspectResult.stderr}`);
    const hostConfig = JSON.parse(inspectResult.stdout);
    assert.equal(hostConfig.Memory, 134_217_728, "The regression fixture must retain the old memory limit");
    assert.equal(hostConfig.MemoryReservation, 256_000_000, "The regression fixture must retain the ZimaOS reservation");
  } else {
    assert.match(
      failingResult.stderr,
      /minimum memory limit can not be less than memory reservation limit/i,
      "Docker must reject the regression fixture with the reported daemon error",
    );
  }
} finally {
  docker(["rm", "--force", failingContainer]);
}

process.stdout.write("Keyku primary and alternative Compose resource and reservation contracts passed.\n");
