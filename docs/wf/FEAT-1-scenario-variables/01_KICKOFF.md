# Kickoff: FEAT-1-scenario-variables

> Issue: #1
> Created: 2026-01-30
> Revision: 1

## Goal

Add variable support to YAML scenarios to enable reusable values (email, password, etc.) that can be interpolated in `do` and `then` actions, reducing duplication and improving maintainability.

## Success Criteria

- [ ] `variables` section can be defined at the top level of scenario YAML
- [ ] Variables can be interpolated in `do` and `then` strings using `(variable_name)` syntax
- [ ] Validation detects undefined variable references
- [ ] Documentation and examples are updated for all affected skills

## Constraints

- Maintain backward compatibility with existing scenarios (no breaking changes)
- Follow existing pattern of natural language actions
- Variable syntax must not conflict with existing Japanese text patterns

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

- [ ] Variable syntax: Use `(var)` as shown in Issue, or `{{ var }}`/`${var}`?
- [ ] Should variables support default values? (e.g., `(var:default)`)
- [ ] Scope: Are variables available in `replay` sections?

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
