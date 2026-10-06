import sys
import argparse
from transcript.detect import detect_format
from transcript.parsers.claude import parse as parse_claude
from transcript.parsers.codex import parse as parse_codex
from transcript.parsers.gemini import parse as parse_gemini
from transcript.renderers.markdown import render, RenderOptions


_EPILOG = """\
interactive viewer:
  transcript view [options] input
                        browse the transcript in a terminal UI instead of
                        printing Markdown
"""


def main():
    # Transcripts are full of non-ASCII (arrows, middle dots, user text); never
    # let a non-UTF-8 locale turn that into a UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="transcript",
        description="Convert agent logs to readable Markdown transcripts.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="?", help="Path to log file")
    parser.add_argument(
        "-f", "--format", choices=["claude", "gemini", "codex"],
        help="Log format (auto-detected if omitted)"
    )
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--no-thinking", action="store_true", help="Exclude thinking blocks")
    parser.add_argument("--no-tools", action="store_true", help="Exclude tool calls")
    parser.add_argument("--no-text", action="store_true", help="Exclude response text")
    parser.add_argument("--no-cost", action="store_true", help="Exclude cost/token info")
    parser.add_argument("--expand-tools", action="store_true", help="Show full tool output")
    parser.add_argument("--pretty", action="store_true", help="Render formatted output in terminal")

    # Handle 'view' subcommand
    argv = sys.argv[1:]
    is_view = False
    if argv and argv[0] == "view":
        is_view = True
        argv = argv[1:]

    args = parser.parse_args(argv)

    if not args.input:
        parser.print_help()
        sys.exit(1)

    try:
        with open(args.input, encoding="utf-8"):
            pass
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(2)
    except OSError as e:
        print(f"Error: cannot read {args.input}: {e.strerror or e}", file=sys.stderr)
        sys.exit(2)

    fmt = args.format
    if not fmt:
        try:
            fmt = detect_format(args.input)
        except (ValueError, RecursionError, OSError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        if fmt == "claude":
            transcript = parse_claude(args.input)
        elif fmt == "codex":
            transcript = parse_codex(args.input)
        else:
            transcript = parse_gemini(args.input)
    except Exception as e:
        print(f"Error: failed to parse {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    if is_view:
        from transcript.tui.app import TranscriptApp
        app = TranscriptApp(transcript)
        app.run(mouse=False)
        return

    options = RenderOptions(
        show_thinking=not args.no_thinking,
        show_tools=not args.no_tools,
        show_text=not args.no_text,
        show_cost=not args.no_cost,
        expand_tools=args.expand_tools,
    )
    md = render(transcript, options)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(md)
        except OSError as e:
            print(f"Error: cannot write {args.output}: {e.strerror or e}", file=sys.stderr)
            sys.exit(1)
    elif args.pretty:
        from rich.console import Console
        from rich.markdown import Markdown
        Console().print(Markdown(md))
    else:
        sys.stdout.write(md)
