# Plan: FEAT-1-scenario-variables

> Spec: [02_SPEC.md](./02_SPEC.md)
> Created: 2026-01-30
> Last Updated: 2026-01-30

## Overview

Implement variable support in 6 steps: schema updates for all test skills, validation rules addition, auto-fix rules addition, template/sample updates, and documentation sync.

## Steps

### Step 1: Update Android Test Schema

- **Purpose:** Add `variables` section definition to Android test scenario schema
- **Files:** `dotclaude/skills/uiai-android-test/references/scenario-schema.md`
- **Tasks:**
  - Add `variables` field to schema table
  - Add interpolation syntax documentation `(variable_name)`
  - Add usage examples with variables
  - Document escape syntax `\(` and `\)`
- **Done when:** Schema includes complete variable documentation
- **Size:** S
- **Depends on:** None

### Step 2: Update Web Test Schema

- **Purpose:** Add `variables` section definition to Web test scenario schema
- **Files:** `dotclaude/skills/uiai-web-test/references/scenario-schema.md`
- **Tasks:**
  - Add `variables` field (same as Android)
  - Ensure consistency with Android schema
- **Done when:** Schema matches Android test schema for variables
- **Size:** S
- **Depends on:** Step 1

### Step 3: Add Validation Rules

- **Purpose:** Add validation rules for variable definitions and references
- **Files:** `dotclaude/skills/uiai-scenario-check/references/validation-rules.md`
- **Tasks:**
  - Add E030: Undefined variable reference
  - Add E031: Invalid variable name
  - Add E032: Duplicate variable definition
  - Add W005: Unused variable (warning)
  - Update validation order section
- **Done when:** All new error codes documented with examples
- **Size:** M
- **Depends on:** Step 1

### Step 4: Add Auto-Fix Rules

- **Purpose:** Add auto-fix rules for variable-related errors
- **Files:** `dotclaude/skills/uiai-scenario-check/references/auto-fix-rules.md`
- **Tasks:**
  - Add E032 fix: Remove duplicate definitions (keep first)
  - Add W005 handling: Suggest removal of unused variables
  - Update auto-fix summary table
- **Done when:** Auto-fix rules documented for applicable errors
- **Size:** S
- **Depends on:** Step 3

### Step 5: Update Template and Samples

- **Purpose:** Add variable usage examples to template and sample files
- **Files:** `template/_template.yaml`, `sample/sample-login.yaml`
- **Tasks:**
  - Add `variables` section to template with commented example
  - Update sample-login.yaml to use variables for credentials
- **Done when:** Template and samples demonstrate variable usage
- **Size:** S
- **Depends on:** Step 1

### Step 6: Sync Japanese Documentation

- **Purpose:** Create/update Japanese translations in docs/readme
- **Files:** `dotclaude/docs/readme/skills.uiai-android-test.md`, etc.
- **Tasks:**
  - Update Android test skill docs (if exists)
  - Update Web test skill docs (if exists)
  - Update scenario-check skill docs (if exists)
- **Done when:** Japanese docs are in sync with English
- **Size:** S
- **Depends on:** Steps 1-4

## Progress

| Step | Title | Status |
|------|-------|--------|
| 1 | Update Android Test Schema | completed |
| 2 | Update Web Test Schema | completed |
| 3 | Add Validation Rules | completed |
| 4 | Add Auto-Fix Rules | completed |
| 5 | Update Template and Samples | completed |
| 6 | Sync Japanese Documentation | completed (skipped - no existing docs) |

## Risks

| Risk | Impact | Prob | Mitigation |
|------|--------|------|------------|
| Syntax conflict with existing scenarios | High | Low | `(var)` is uncommon in Japanese text; escape syntax provided |
| Missing validation edge cases | Medium | Medium | Comprehensive examples in validation rules |
| Documentation inconsistency across platforms | Low | Medium | Copy-paste from Step 1 to Step 2 |

## Rollback

All changes are documentation only (markdown files). Rollback is straightforward:
1. `git checkout` affected files
2. No runtime code changes

## Notes

- Variable interpolation logic is implemented by the AI agent at runtime, not hardcoded
- Schema changes are declarative - the agent reads the schema and applies it
- Testing is manual: run actual scenarios with variables to verify
