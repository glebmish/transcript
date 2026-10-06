# Security

## Threat model

`transcript` reads agent session logs and prints their content to a terminal, a Markdown file, or a terminal UI. Log content is untrusted: it includes model output, tool output, and file contents the agent read.

The tool deliberately neutralizes that content instead of passing it through:

- Terminal control characters (ANSI/CSI and OSC sequences such as clipboard writes or title changes, C1 controls, lone carriage returns) are replaced with visible, inert stand-ins. See "Control Characters" in [`docs/specs/presentation.md`](docs/specs/presentation.md#control-characters).
- In the TUI, log text is never interpreted as Textual markup. See "Untrusted Text" in [`docs/specs/renderers/tui.md`](docs/specs/renderers/tui.md#untrusted-text).
- In Markdown output, code fences and spans are sized so log content cannot close them early. See "Tool Calls" in [`docs/specs/renderers/markdown.md`](docs/specs/renderers/markdown.md#tool-calls).

A way to get a terminal to execute a sequence from a log, or to break out of those protections, is a security issue.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**. Don't open a public issue.

## Supported versions

Only the latest release is supported.
