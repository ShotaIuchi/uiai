# Plan: FEAT-1-scenario-variables

> Spec: [02_SPEC.md](./02_SPEC.md)
> Created: 2026-01-30
> Last Updated: 2026-02-02
> Revision: 2

## Overview

Implement variable support in two phases:
- **Phase 1 (Revision 1):** Basic variable definition and interpolation - COMPLETED
- **Phase 2 (Revision 2):** Interactive variable input for null values - IN PROGRESS

Phase 2 adds support for null-value variables that trigger interactive prompts at test execution time.

## Steps

---

## Phase 1: Basic Variable Support (Revision 1) - COMPLETED

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

## Progress (Phase 1)

| Step | Title | Status |
|------|-------|--------|
| 1 | Update Android Test Schema | completed |
| 2 | Update Web Test Schema | completed |
| 3 | Add Validation Rules | completed |
| 4 | Add Auto-Fix Rules | completed |
| 5 | Update Template and Samples | completed |
| 6 | Sync Japanese Documentation | completed (skipped - no existing docs) |

---

## Phase 2: Interactive Variable Input (Revision 2) - IN PROGRESS

### Step 7: Update Schema for Null Variables

- **Purpose:** Add null value and prompt configuration support to variables schema
- **Files:**
  - `dotclaude/skills/uiai-android-test/references/scenario-schema.md`
  - `dotclaude/skills/uiai-web-test/references/scenario-schema.md`
  - `dotclaude/skills/uiai-ios-test/references/scenario-schema.md`
- **Tasks:**
  - Document null value as trigger for interactive prompt
  - Add object syntax for variables with custom prompt message
  - Add examples for interactive variable usage
  - Document CI/headless environment behavior
- **Done when:** All three schemas document null variable behavior
- **Size:** M
- **Depends on:** Phase 1 complete

### Step 8: Add Interactive Prompt Documentation

- **Purpose:** Document execution flow for interactive variable input
- **Files:**
  - `dotclaude/skills/uiai-android-test/references/execution-flow.md`
  - `dotclaude/skills/uiai-web-test/references/execution-flow.md`
  - `dotclaude/skills/uiai-ios-test/references/execution-flow.md`
- **Tasks:**
  - Add variable collection phase before test execution
  - Document prompt format and user interaction
  - Document non-interactive environment skip behavior
  - Add flow diagram for variable resolution
- **Done when:** Execution flow clearly describes when and how prompts occur
- **Size:** M
- **Depends on:** Step 7

### Step 9: Add W006 Validation Rule

- **Purpose:** Add warning for null-value variables
- **Files:** `dotclaude/skills/uiai-scenario-check/references/validation-rules.md`
- **Tasks:**
  - Add W006: Variable has null value (will prompt at runtime)
  - Document that this is a warning, not an error
  - Update validation order section
- **Done when:** W006 is documented with examples
- **Size:** S
- **Depends on:** Step 7

### Step 10: Update Templates with Interactive Examples

- **Purpose:** Add interactive variable examples to template and samples
- **Files:**
  - `template/_template.yaml`
  - `sample/sample-login.yaml`
- **Tasks:**
  - Add commented example of null-value variable
  - Add example with custom prompt message
  - Document when to use interactive vs hardcoded values
- **Done when:** Templates demonstrate both usage patterns
- **Size:** S
- **Depends on:** Step 7

## Progress (Phase 2)

| Step | Title | Status |
|------|-------|--------|
| 7 | Update Schema for Null Variables | completed |
| 8 | Add Interactive Prompt Documentation | completed |
| 9 | Add W006 Validation Rule | completed |
| 10 | Update Templates with Interactive Examples | completed |

## Risks

| Risk | Impact | Prob | Mitigation |
|------|--------|------|------------|
| Syntax conflict with existing scenarios | High | Low | `(var)` is uncommon in Japanese text; escape syntax provided |
| Missing validation edge cases | Medium | Medium | Comprehensive examples in validation rules |
| Documentation inconsistency across platforms | Low | Medium | Copy-paste from Step 1 to Step 2 |
| CI environment hangs waiting for input | High | Medium | Document skip behavior; detect non-interactive environment |
| Confusion between null and empty string | Medium | Medium | Clear documentation distinguishing null (prompt) vs "" (valid) |
| Interactive prompt UX inconsistency | Low | Low | Standardize prompt format across all test skills |

## Rollback

All changes are documentation only (markdown files). Rollback is straightforward:
1. `git checkout` affected files
2. No runtime code changes

## Notes

- Variable interpolation logic is implemented by the AI agent at runtime, not hardcoded
- Schema changes are declarative - the agent reads the schema and applies it
- Testing is manual: run actual scenarios with variables to verify
- Interactive prompts are handled by the agent, not a hardcoded prompt library
- Non-interactive detection relies on terminal/stdin availability

## Revision History

| Revision | Date | Description |
|----------|------|-------------|
| 1 | 2026-01-30 | Initial plan: Phase 1 basic variable support (Steps 1-6) |
| 2 | 2026-02-02 | Added Phase 2: Interactive variable input (Steps 7-10) |
