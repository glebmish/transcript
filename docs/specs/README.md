# Transcript Specs

These specs are organized around a docs-first contract for adding and presenting agent logs.

## Reading Order

1. `common-model.md` defines the normalized data model all parsers produce.
2. `presentation.md` defines how each supported common log piece should be presented, independent of source agent and renderer.
3. `agents/*.md` defines how each native agent log format maps into the common model.
4. `renderers/*.md` defines how each output surface realizes the common presentation contract.

## Ownership Rules

- Common model docs own field meaning and parser output contracts.
- Common presentation docs own standard semantics for visible transcript pieces.
- Agent docs own native-format mapping only.
- Renderer docs own Markdown/TUI layout and interaction only.

When implementation changes, update the owning spec rather than duplicating the rule in another file.
