# Revisions: FEAT-1-scenario-variables

> Work ID: FEAT-1-scenario-variables
> Created: 2026-02-02

## Revision 3 (2026-02-02)

### Trigger

User instruction via `/ghwf1-kickoff revise`:
> 変数定義だけで値が設定されてない場合は、テスト実行時に変数に何を設定させるか対話式で設定させたい

### Summary

Clarify the interactive variable input feature requirements and add implementation details.

### Changes

- **01_KICKOFF.md:**
  - Updated revision number to 3
  - Added detailed use cases for interactive input
  - Clarified execution flow with Japanese prompt examples
  - Added implementation notes (prompt timing, CI handling, null vs empty string)
  - Simplified validation changes (W006 only, removed E033)

### Clarifications

| Item | Clarification |
|------|---------------|
| Prompt Timing | All null-value variables prompted **before** test starts, not during |
| null vs "" | `null` = prompt at runtime; `""` = valid empty value (no prompt) |
| CI/Headless | Skip test with clear message when interactive prompt is needed |
| Batch Prompt | Multiple null variables prompted together, not one at a time |

### Next Steps

1. Update 02_SPEC.md with clarified requirements
2. Update 03_PLAN.md with implementation tasks for interactive mode
3. Update scenario-schema.md with null value documentation
4. Add W006 to validation-rules.md
5. Implement interactive prompt in test execution skills

---

## Revision 2 (2026-02-02)

### Trigger

GitHub Issue #1 Comment by @ShotaIuchi:
> 変数定義だけで値が設定されてない場合は、テスト実行時に変数に何を設定させるか対話式で設定させたい

### Summary

Add support for interactive variable input when variable values are not set (null).

### Changes

- **01_KICKOFF.md:**
  - Updated Goal to include interactive variable input enhancement
  - Added new Success Criteria for interactive mode
  - Added constraints for CI/automated environments
  - Updated Open Questions with new considerations
  - Added detailed "Interactive Variable Input" section in Notes

### New Requirements

| Requirement | Description |
|-------------|-------------|
| Interactive Prompt | Variables with `null` value trigger user prompt before test execution |
| CI Compatibility | Non-interactive environments must have fallback behavior |
| Validation Warning W006 | Warn about variables with null values |

### Next Steps

1. Update 02_SPEC.md with detailed functional requirements for interactive mode
2. Update 03_PLAN.md with implementation tasks
3. Implement interactive prompt logic in test execution skills
4. Update validation rules (W006)
5. Update documentation and examples

---

## Revision 1 (2026-01-30)

### Trigger

Initial implementation from GitHub Issue #1.

### Changes

- Initial kickoff, spec, and plan documents created
- Basic variable support implemented with `(variable_name)` syntax
- Validation rules E030-E032 and W005 added
- Documentation updated for all affected skills
