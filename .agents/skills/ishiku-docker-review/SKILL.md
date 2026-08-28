---
name: ishiku-docker-review
description: Review, harden, build, and smoke-test Docker delivery for an ishiku app. Use for Dockerfiles, Compose, central port allocation, build contexts, runtime users, health checks, persistence, secrets, networking, multi-architecture images, or container release readiness.
---

# ishiku Docker review

## Inputs

Read Dockerfiles, Compose files, `.dockerignore`, runtime/write paths, ports, health/readiness endpoints, secret sources, volumes, reverse-proxy assumptions, architectures, and upgrade/backup requirements. In the central ishiku workspace, also read the workspace-root `ports.yaml` before changing a published host port.

## Central port registry

Treat workspace-root `ports.yaml` as the canonical source for ishiku application host ports. Resolve the application by `.ishiku/project.yaml` `application.id`, then find the explicit port entry whose `application_id` matches it.

- `assigned` with `assignment_state: active` must match AppSpec, Compose, `.env.example`, manifests, and documentation.
- `reserved` with `planned` or `reassign` is a target allocation. Do not mark it active until configuration and deployment evidence exist.
- Allocate only an `available` and assignable port through the registry workflow, persist the reservation before editing an app, and never take or silently reassign another application's port.
- The registry controls the published host port only. Preserve the application's compatible container port unless an approved migration changes it.
- A publishable app repository must materialize the resolved value and remain runnable from a standalone clone; it must not depend on the outer workspace file at runtime.

A missing application entry, duplicate assignment, invalid state, or mismatch between the active registry entry and published Compose is a release blocker.

## Workflow

1. Prove the build context stays inside the cloned repository and excludes Git, private data, secrets, databases, backups, tests not needed at runtime, and local artifacts.
2. Pin minimal supported bases; use reproducible multi-stage builds and a non-root runtime. Drop capabilities, disable privilege escalation, prefer read-only root, bound resources, and mount only required writable paths.
3. Validate configuration and secrets at startup. Do not bake secrets or ship default credentials.
4. Add liveness/readiness checks, graceful shutdown, persistence ownership, logging bounds, and explicit network exposure. For ZimaOS, use the resolved registry port as a direct scalar in the primary Compose file; keep environment interpolation in an explicitly documented alternative Compose path only.
5. Run Compose config validation, image build, image inspection, secret/SBOM/vulnerability scans, non-root/read-only checks, startup/health/API smoke, restart, persistence, backup/restore, and upgrade tests. Test declared architectures in CI.
6. Record image digest and exact Docker/Compose versions.

Never infer a build from syntax validation, use `latest` for a release, run privileged without an approved exception, expose an admin service by default, or report `VERIFIED` when the daemon/build/smoke test was unavailable.

## Output and completion

Report build context, base/digest, user/capabilities/filesystem, ports/volumes/secrets, health, scan/SBOM, build and runtime evidence, persistence/restore/upgrade, and residual findings. Missing Docker execution evidence yields `IMPLEMENTED_BUT_NOT_VERIFIED`.
