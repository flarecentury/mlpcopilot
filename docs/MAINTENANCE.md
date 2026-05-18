# Documentation Maintenance

Use this checklist when adding, moving, or reviewing documentation. The goal is
to keep docs easy to update without mixing product requirements, runtime
behavior, and plugin-specific scientific methods.

## Source Of Truth

| Source | Use For |
| --- | --- |
| [`../prd/`](../prd/) | Product requirements, boundary decisions, current priorities |
| [`../README.md`](../README.md) | Public entrypoint, quick start, high-level status |
| [`../AGENTS.md`](../AGENTS.md) | Development rules and repository-specific guardrails |
| [`docs/`](./README.md) | Current implementation usage, operation, and maintenance notes |
| [`docs/upstream/`](./upstream/) | Inherited reference material only |

When docs disagree, prefer this order: PRD, repository rules, implementation,
operational docs, upstream reference. Update the stale document in the same
change whenever possible.

## Placement Rules

| If the document is about... | Put it in... |
| --- | --- |
| Runtime/plugin architecture, workspace schema, UI read models | [`design/`](./design/) |
| Agent memory, context injection, long-running runtime behavior | [`runtime/`](./runtime/) |
| Commands, config keys, API routes, SDK calls | [`reference/`](./reference/) |
| Deployment, service management, multiple local instances | [`operations/`](./operations/) |
| Inherited general-purpose behavior not enabled by MLP defaults | [`upstream/`](./upstream/) |
| Requirements or future product decisions | [`../prd/`](../prd/) |

Do not put dataset validation algorithms, checkpoint inference methods, DP-GEN
scientific logic, or benchmark methodology into runtime docs. Those belong in
MCP/skill docs or the relevant plugin package.

## Review Checklist

Before finishing a doc change:

- Confirm the document is in the right directory.
- Update [`README.md`](./README.md) and the relevant subdirectory index.
- Check relative links after moves or renames.
- Keep command examples runnable from the repository root unless stated
  otherwise.
- Mark defaults as defaults, not forced migration behavior.
- Preserve explicit user config semantics: defaults apply when a field is
  absent, and user-provided allowlists/enabled lists stay exact.
- Keep approval claims concrete: destructive or state-changing actions must go
  through the runtime approval policy when invoked through the agent.
- Keep scientific metrics tied to tool artifacts, not LLM judgment.
- Avoid past-tense implementation claims unless the code path exists.
- Keep upstream docs clearly labeled as inherited reference material.

## Document Shape

Prefer this shape for new docs:

1. Title.
2. One paragraph explaining scope.
3. Links to source-of-truth PRDs or code paths when relevant.
4. Stable sections ordered from common use to advanced details.
5. A short maintenance note if the doc mirrors config, CLI, or API behavior.

Avoid adding long narrative goals, duplicated PRD text, or large pasted
scientific payloads. Scientific data should be referenced by file path, artifact
ID, or tool output.

## Rename Workflow

When moving docs:

1. Move the file into the right directory.
2. Update all local links with `rg`.
3. Update [`docs/README.md`](./README.md).
4. Update the subdirectory `README.md`.
5. Run a lightweight link/path check.

The repository may still contain inherited upstream docs. Move inherited docs
under [`upstream/`](./upstream/) instead of rewriting them into product defaults.
