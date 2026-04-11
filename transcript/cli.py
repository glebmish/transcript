import shutil
import subprocess
import sys
import argparse
from transcript.detect import detect_format
from transcript.parsers.claude import parse as parse_claude
from transcript.parsers.gemini import parse as parse_gemini
from transcript.renderers.markdown import render, RenderOptions


def main():
    parser = argparse.ArgumentParser(
        description="Convert agent logs to readable Markdown transcripts."
    )
    parser.add_argument("input", nargs="?", help="Path to log file")
    parser.add_argument(
        "-f", "--format", choices=["claude", "gemini"],
        help="Log format (auto-detected if omitted)"
    )
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--no-thinking", action="store_true", help="Exclude thinking blocks")
    parser.add_argument("--no-tools", action="store_true", help="Exclude tool calls")
    parser.add_argument("--no-text", action="store_true", help="Exclude response text")
    parser.add_argument("--no-cost", action="store_true", help="Exclude cost/token info")
    parser.add_argument("--expand-tools", action="store_true", help="Show full tool output")
    parser.add_argument("--glow", action="store_true", help="Render markdown with glow")

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
        with open(args.input):
            pass
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    fmt = args.format
    if not fmt:
        try:
            fmt = detect_format(args.input)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        if fmt == "claude":
            transcript = parse_claude(args.input)
        else:
            transcript = parse_gemini(args.input)
    except Exception as e:
        print(f"Error: failed to parse {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    if is_view:
        from transcript.tui.app import TranscriptApp
        app = TranscriptApp(transcript)
        app.run()
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
        with open(args.output, "w") as f:
            f.write(md)
    elif args.glow:
        glow_bin = shutil.which("glow")
        if not glow_bin:
            print("Error: glow not found in PATH. Install it: https://github.com/charmbracelet/glow", file=sys.stderr)
            sys.exit(1)
        proc = subprocess.run([glow_bin, "-"], input=md, text=True)
        sys.exit(proc.returncode)
    else:
        sys.stdout.write(md)
