# Kickoff: FEAT-1-scenario-variables

> Issue: #1
> Created: 2026-01-30
> Revision: 3

## Goal

Add variable support to YAML scenarios to enable reusable values (email, password, etc.) that can be interpolated in `do` and `then` actions, reducing duplication and improving maintainability.

**Enhancement (Revision 2-3):** Support interactive variable input when variable values are not set (null), enabling runtime prompts for test data. Users can define variables without values, and the test execution will prompt for input before starting.

## Success Criteria

- [x] `variables` section can be defined at the top level of scenario YAML
- [x] Variables can be interpolated in `do` and `then` strings using `(variable_name)` syntax
- [x] Validation detects undefined variable references
- [x] Documentation and examples are updated for all affected skills
- [ ] **NEW:** Variables with null/empty values trigger interactive prompts at test execution time
- [ ] **NEW:** Interactive mode allows users to input variable values before test starts
- [ ] **NEW:** Validation warns (W006) about variables with null values

## Constraints

- Maintain backward compatibility with existing scenarios (no breaking changes)
- Follow existing pattern of natural language actions
- Variable syntax must not conflict with existing Japanese text patterns
- Interactive mode must not block automated/CI environments (provide fallback or skip)

## Non-goals

- Environment-specific variables (env vars, secrets) - future enhancement
- Cross-scenario variable sharing
- Dynamic variable values computed at runtime

## Dependencies

### Depends on

- None

### Impacts

- `uiai-android-test` skill
- `uiai-web-test` skill
- `uiai-ios-test` skill
- `uiai-scenario-check` skill (validation/auto-fix)

### Conflicts

- None currently

## Open Questions

- [x] Variable syntax: Use `(var)` as shown in Issue, or `{{ var }}`/`${var}`? → **Decided: `(var)` syntax**
- [ ] Should variables support default values? (e.g., `(var:default)`)
- [x] Scope: Are variables available in `replay` sections? → **Yes**
- [ ] **NEW:** How should interactive mode behave in CI/headless environments?
- [ ] **NEW:** Should `null` and empty string `""` be treated differently?

## Notes

### Issue Description Summary

The Issue proposes adding a `values` section (using `(variable)` interpolation syntax):

```yaml
values:
  address: hogehoge@fuga.com
  password: 1234567890

steps:
  - id: "section1"
    actions:
      - do: "address in (address)"
      - do: "password in (password)"
```

### Files to Modify

| File | Change |
|------|--------|
| `skills/uiai-android-test/references/scenario-schema.md` | Add `variables` section spec |
| `skills/uiai-web-test/references/scenario-schema.md` | Add `variables` section spec |
| `skills/uiai-scenario-check/references/validation-rules.md` | Add variable validation |
| `skills/uiai-scenario-check/references/auto-fix-rules.md` | Add variable-related fixes |
| `template/_template.yaml` | Add variable example |
| `sample/sample-login.yaml` | Add variable usage example |

### New Feature: Interactive Variable Input (Revision 2-3)

**Issue Comment Request:**
> 変数定義だけで値が設定されてない場合は、テスト実行時に変数に何を設定させるか対話式で設定させたい

**Use Case:**
- テスト作成者が機密情報（パスワード、APIキー等）をYAMLに直接書きたくない
- 環境によって異なる値を実行時に入力したい
- チームで共有するシナリオで、各自の認証情報を使いたい

**Proposed Schema Change:**

```yaml
variables:
  # Standard variable with value (no prompt)
  email: "test@example.com"

  # Variable requiring interactive input (null value)
  password: null

  # Alternative: explicit prompt configuration with custom message
  secret_key:
    value: null
    prompt: "Enter your secret key"
```

**Execution Flow:**

1. Load scenario YAML
2. Parse `variables` section
3. **Detect null-value variables** - variables where value is `null` or explicitly omitted
4. **Before test execution starts**, prompt user for each null-value variable:
   ```
   === 変数入力が必要です ===

   Variable 'password' is not set.
   Enter value for password: ********

   Variable 'secret_key' is not set.
   Enter your secret key: ________

   === 変数入力完了 ===
   ```
5. Store provided values in memory for test execution
6. Interpolate variables in `do` and `then` actions
7. Continue with normal test flow

**Implementation Notes:**
- Prompt all null-value variables **together** before test starts (not during test)
- Support password masking for sensitive inputs (optional, future enhancement)
- In non-interactive (CI) environments, skip test with clear message
- Empty string `""` is a valid value (no prompt)
- `null` explicitly means "prompt at runtime"

**Validation Changes:**

| Code | Description | Behavior |
|------|-------------|----------|
| W006 | Variable has null value | Warning (not error) - will prompt at runtime |

> Note: Empty string `""` is a valid value and does not trigger prompt or warning.
