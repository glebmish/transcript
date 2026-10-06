# Agent Format Specs

Each file here maps one native log format to the common model in `docs/specs/common-model.md`:

- `claude.md`: Claude Code JSONL
- `gemini.md`: Gemini CLI JSON
- `codex.md`: Codex CLI/Desktop JSONL
- `template.md`: blank mapping to copy for a new format

## Implementing a new agent format

Start by copying `template.md` to `<key>.md` and filling it in from real logs on your machine (they never go into the repo). Then:

1. **Parser.** Add `transcript/parsers/<key>.py` exposing `parse(path: str) -> Transcript`.
   - Treat every native field as untrusted: read nested values through the `as_dict`, `as_list`, `as_str` and `as_int` coercions in `transcript/parsers/common.py`, so null or wrong-typed fields degrade to empty values instead of aborting.
   - Use `is_real_model()` from the same module when building the model set and pricing, so placeholder models are neither listed nor priced.
   - There is no shared base: each parser has its own `_parse_ts` and `_build_transcript`. Copy them from an existing parser and keep the contract they implement:
     - totals: `models` holds only real assistant models; `total_tokens_in`/`total_tokens_out` sum per-message tokens; `tool_stats` counts `PASSED`, `FAILED` and `CANCELLED` calls;
     - cost: sum `estimate_cost()` over real-model assistant messages; set `cost_is_partial=True` when any of them returns `None`; `total_cost` is `None` (`final_cost = None`) when there are no models or when cost is partial and nothing could be priced;
     - timestamps: a missing or unparseable timestamp is UTC `datetime.min`; prefer the native session start/end when the format has them and fall back to the first/last parsed message timestamp. Document the exact fallbacks in your spec.
   - Warn on stderr for skipped malformed entries, with a line or entry number.
2. **Detection.** Extend `transcript/detect.py`. Gemini is tried first, by parsing the whole file as one JSON object. Otherwise JSONL lines are scanned in order and the first recognizable line decides the format; on each line, Codex types are checked before Claude types. Add your format's `type` set so it does not overlap the existing `_CLAUDE_TYPES` and `_CODEX_TYPES`, and update "Detection Contract" in `docs/specs/common-model.md`.
3. **CLI.** In `transcript/cli.py`, add the key to the `--format` choices and a branch in the parser dispatch. The final `else` falls through to Gemini, so the new branch must come before it.
4. **Pricing.** Add the format's model prices to `PRICING` in `transcript/pricing.py` (USD per 1M input/output tokens, keyed by model-id prefix), or state in the spec that its models are deliberately unpriced, as Codex does.
5. **Sanitizing.** Pass any log-derived text you print in a stderr warning through `sanitize_text()` from `transcript/sanitize.py`. Renderers already sanitize their own output.
6. **Tests.** Add a synthetic fixture under `tests/fixtures/` (never a real log), `tests/test_<key>_parser.py`, and cases in `tests/test_detect.py` and `tests/test_cli.py` (auto-detection and `--format <key>`).
7. **Docs.** Add the format to the log-location table and the `--format` list in `README.md`, and add `parsers/<key>.py` to the structure block in both `CLAUDE.md` and `AGENTS.md`.
