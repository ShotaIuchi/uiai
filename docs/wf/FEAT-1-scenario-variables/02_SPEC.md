# Spec: FEAT-1-scenario-variables

> Kickoff: [01_KICKOFF.md](./01_KICKOFF.md)
> Created: 2026-01-30
> Last Updated: 2026-02-02
> Revision: 2

## Overview

Add variable support to scenario YAML files, enabling test data reuse and reducing duplication. Variables are defined in a `variables` section and interpolated in `do` and `then` actions using `(variable_name)` syntax.

**Enhancement (Revision 2):** Support interactive variable input when variable values are null or empty, enabling runtime prompts for test data entry.

## Scope

### In Scope

- `variables` top-level section in scenario YAML
- Variable interpolation in `do` and `then` strings
- Validation of variable definitions and references
- Auto-fix for common variable errors
- Documentation and examples

### Out of Scope

- Environment variables / secrets (future enhancement)
- Cross-scenario variable sharing
- Dynamic/computed variables at runtime
- Nested variable references (variables referencing other variables)
- Password masking in terminal output (future enhancement)

## Users / Use-cases

| User | Use-case | Priority |
|------|----------|----------|
| Test Author | Reuse login credentials across multiple steps | High |
| Test Author | Change test data in one place for multiple scenarios | High |
| Test Author | Make scenarios more readable by using named values | Medium |
| Test Author | Enter sensitive credentials at runtime without storing in YAML | High |
| Test Author | Prompt for environment-specific values during test execution | Medium |

## Functional Requirements

### Core Variable Support (Revision 1)

- FR-1: Scenario YAML supports a `variables` section at top level
- FR-2: Variables can be referenced using `(variable_name)` syntax in `do` and `then` strings
- FR-3: Variable names must follow `[a-zA-Z_][a-zA-Z0-9_]*` pattern
- FR-4: Undefined variable references produce validation error
- FR-5: Variables are interpolated before action execution
- FR-6: Literal parentheses can be escaped as `\(` and `\)`

### Interactive Variable Input (Revision 2)

- FR-7: Variables with `null` value trigger interactive prompt before test execution
- FR-8: Interactive prompt displays variable name and waits for user input
- FR-9: All null-value variables are collected and prompted together before test starts
- FR-10: User-provided values are stored in memory for the duration of test execution
- FR-11: Empty string `""` is treated as valid value (no prompt triggered)
- FR-12: In CI/headless environments, null variables should cause test skip with clear message

## Non-functional Requirements

- NFR-1: Backward compatible - existing scenarios without variables continue to work
- NFR-2: No runtime performance impact beyond string interpolation
- NFR-3: Clear error messages for invalid variable usage

## Acceptance Criteria

### AC-1: Basic Variable Definition and Usage

- **Given:** A scenario with `variables: { email: "test@example.com" }`
- **When:** An action contains `do: "input (email) in email field"`
- **Then:** The action is executed with `do: "input test@example.com in email field"`

### AC-2: Undefined Variable Reference Error

- **Given:** A scenario using `(undefined_var)` without definition
- **When:** Validation is run
- **Then:** Error E030 is reported: "Undefined variable: undefined_var"

### AC-3: Multiple Variables in Single Action

- **Given:** Variables `{ user: "john", domain: "example.com" }`
- **When:** Action is `do: "input (user)@(domain) in email field"`
- **Then:** Interpolated as `do: "input john@example.com in email field"`

### AC-4: Variables in then Assertions

- **Given:** Variables `{ expected_office: "Tokyo HQ" }`
- **When:** Action is `then: "「(expected_office)」と表示されていること"`
- **Then:** Verified as `then: "「Tokyo HQ」と表示されていること"`

### AC-5: Escaped Parentheses

- **Given:** Action `do: "Calculate \(1+2\) result"`
- **When:** Interpolation is applied
- **Then:** Literal parentheses preserved: `do: "Calculate (1+2) result"`

### AC-6: Interactive Prompt for Null Variables (Revision 2)

- **Given:** A scenario with `variables: { password: null }`
- **When:** Test execution starts
- **Then:** User is prompted: `Variable 'password' is not set. Enter value for password:`
- **And:** After user enters value, test continues with provided value

### AC-7: Multiple Null Variables Prompted Together (Revision 2)

- **Given:** A scenario with `variables: { email: null, password: null, api_key: null }`
- **When:** Test execution starts
- **Then:** All three variables are prompted sequentially before test begins
- **And:** Test only starts after all values are provided

### AC-8: Null Variable Validation Warning (Revision 2)

- **Given:** A scenario with `variables: { secret: null }`
- **When:** Validation is run with `uiai-scenario-check`
- **Then:** Warning W006 is reported: "Variable 'secret' has null value (will prompt at runtime)"
- **And:** Validation passes (warning, not error)

### AC-9: CI/Headless Environment Handling (Revision 2)

- **Given:** A scenario with null variables running in non-interactive environment
- **When:** Interactive prompt would be triggered
- **Then:** Test is skipped with message: "Skipped: variables [password, api_key] require interactive input"

## Affected Components

| Component | Impact | Notes |
|-----------|--------|-------|
| `uiai-android-test` | High | Schema update, interpolation logic |
| `uiai-web-test` | High | Schema update, interpolation logic |
| `uiai-ios-test` | High | Schema update, interpolation logic |
| `uiai-scenario-check` | High | New validation rules E030-E033 |
| Template/Samples | Medium | Add variable examples |

## Detailed Changes

### Schema Change: variables Section

**Before:**
```yaml
name: "ログインテスト"
app:
  android: "com.example.app"
steps:
  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「test@example.com」を入力"
      - do: "パスワード欄に「password123」を入力"
```

**After:**
```yaml
name: "ログインテスト"
app:
  android: "com.example.app"

variables:
  email: "test@example.com"
  password: "password123"

steps:
  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「(email)」を入力"
      - do: "パスワード欄に「(password)」を入力"
```

**Interactive Variable Example (Revision 2):**

```yaml
name: "本番ログインテスト"
app:
  android: "com.example.app"

variables:
  # Hardcoded test email (no prompt)
  email: "test@example.com"
  # Will prompt user at runtime
  password: null
  # Alternative: explicit prompt configuration
  api_key:
    value: null
    prompt: "Enter your API key"

steps:
  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「(email)」を入力"
      - do: "パスワード欄に「(password)」を入力"
```

### Validation Rules Addition

**New Error Codes:**

| Code | Description | Auto-fix |
|------|-------------|----------|
| E030 | Undefined variable reference | No |
| E031 | Invalid variable name | No |
| E032 | Duplicate variable definition | Yes (keep first) |
| W005 | Unused variable definition | No (suggest removal) |
| W006 | Variable has null value (will prompt at runtime) | No |

> Note: E033 (Empty variable value) removed - empty string `""` is a valid value.

### Auto-fix Rules Addition

| Error | Fix |
|-------|-----|
| E032 | Remove duplicate variable definitions, keep first occurrence |
| W005 | Suggest removing unused variable definitions |
| W006 | No auto-fix (intentional design for interactive input) |

## API Changes

None - this is a YAML schema change only.

## Data Changes

### YAML Schema Addition

```yaml
# New optional top-level field
variables:
  type: object
  additionalProperties:
    oneOf:
      - type: string
      - type: "null"
      - type: object
        properties:
          value:
            oneOf:
              - type: string
              - type: "null"
          prompt:
            type: string
            description: "Custom prompt message for interactive input"
  description: "Key-value pairs for variable definitions. Null values trigger interactive prompts."
```

### Variable Name Pattern

```regex
^[a-zA-Z_][a-zA-Z0-9_]*$
```

### Interpolation Pattern

```regex
(?<!\\)\(([a-zA-Z_][a-zA-Z0-9_]*)\)
```

- Matches `(variable_name)` but not `\(escaped)`
- Captures variable name in group 1

## UI Changes

None - CLI only.

## Test Strategy

- **Unit Tests:** Variable interpolation function, regex matching
- **Integration Tests:** Full scenario execution with variables
- **Manual Tests:** Validate sample scenarios with variables work on real devices
- **Interactive Tests (Revision 2):** Verify prompt behavior for null variables
- **CI Tests (Revision 2):** Verify skip behavior in non-interactive environments

## Assumptions

- [x] Issue proposes `values` as key, but `variables` is clearer - decided to use `variables`
- [x] Issue shows `(variable)` syntax - confirmed as the chosen syntax

## Open Questions

- [ ] Should we support default values? e.g., `(var:default)`
- [x] Should variables be available in `replay` sections? (Recommendation: Yes) -> **Decided: Yes**
- [ ] Should we support variable type hints? e.g., `variables: { count: 5 }` as number
- [ ] How should interactive mode behave in CI/headless environments? (Recommendation: Skip with message)
- [ ] Should `null` and empty string `""` be treated differently? (Recommendation: Yes - null prompts, empty string is valid value)

## References

- GitHub Issue #1: シナリオに変数の概念を追加する
- GitHub Issue #1 Comment: 対話式変数入力の要望
- Current scenario-schema.md
- Current validation-rules.md

## Revision History

| Revision | Date | Description |
|----------|------|-------------|
| 1 | 2026-01-30 | Initial spec: variable definition and interpolation |
| 2 | 2026-02-02 | Added interactive variable input for null values (Issue comment feedback) |
