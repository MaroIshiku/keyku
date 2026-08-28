# ishiku design system

The single normative design contract is [`../design-system/contract.json`](../design-system/contract.json). It is English, schema-backed, and optimized for direct machine consumption. Load that file once for design or UI work; do not reconstruct the system from app screenshots, legacy prompts, or repository-local copies.

The contract defines the complete shared identity, foundations, six light/dark palettes, component APIs, composition patterns, responsive behavior, English content rules, WCAG 2.2 AA requirements, authentication-profile presentation, app-icon generation and validation rules, and verification matrix. Security, architecture, testing, and release behavior remain authoritative in their dedicated policies linked by the contract.

App repositories contain only implementation tokens/components, icons they use, executable checks, and `.ishiku/design-system.lock`. The lock records the central contract version and local implementation checksums; it is not a copy of the specification. A standalone clone verifies its implementation with:

```text
node .ishiku/kit/scripts/design-system verify .
```

From the workspace, validate or bind the canonical contract with:

```text
node .ishiku/scripts/design-system validate
node .ishiku/scripts/design-system bind <app-workspace>
node .ishiku/scripts/design-system get <json.path>
```

Use `get` to load only the relevant contract section, for example `tokens.color`, `components.Button`, or `verification`. A standalone clone can refresh implementation checksums after an intentional UI change with `node .ishiku/kit/scripts/design-system bind .`; this cannot change the locked central contract identity or version.

Use `$ishiku-icon-generator` whenever an ishiku app needs a new launcher icon, favicon, PWA icon, webapp import bundle, or replacement explicitly authorized by the task. The skill reads `app_icons` from the central contract, creates and preserves one canonical RGBA `icon-source.png`, directly downsamples every required PNG without crop or mask changes, prepares merge-safe manifest and HTML fragments, and rejects output that fails source, alpha-margin, size, or small-rendering validation. SVG remains optional for genuinely vector artwork. Do not copy the full `app_icons` contract into an app repository.

Any new primitive, token value, navigation model, or design exception requires a recorded override or a central contract change. Visual baselines always require human approval and must never update automatically in CI.
