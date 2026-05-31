---
name: tui-share
description: Use when the user needs to see a TUI artifact they can't view as a local file — converts ANSI-styled terminal text to a PNG, or takes an existing PNG/GIF, uploads it to Cloudinary, and returns a signed URL to paste in chat. Covers the encode → (optional annotate) → upload pipeline. For annotations (arrows, boxes, callouts) see `annotate.md`.
---

# Sharing a TUI artifact as a viewable URL

Two pipelines start from different inputs but end the same way:

- **ANSI text → PNG → upload**: typical for a single captured screen. Use `ansi-to-image` section below.
- **Existing PNG/GIF → upload**: when the image already exists (e.g., a GIF produced by `tui-record`, or an already-annotated PNG). Skip directly to the upload section.

For adding visual callouts (arrows, boxes, text labels) before upload, see the `annotate.md` sub-file — loaded only when you actually need annotations, since most shares skip them.

## When to use

- The user is on a chat / mobile / remote control where local file paths aren't useful.
- You want a durable, signed URL (not TTL-expiring).
- You have an ANSI capture (from `tui-interact`), a static PNG, or a GIF (from `tui-record`) to share.

## Prerequisites

- `textimg` on PATH (only needed for ANSI→PNG). Install: `go install github.com/jiro4989/textimg/v3@latest`.
- JetBrainsMono Nerd Font at `~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf`. Install: `brew install --cask font-jetbrains-mono-nerd-font`.
- `cld` on PATH. Install: `pipx install cloudinary-cli`.
- `CLOUDINARY_URL` exported: `cloudinary://<API_KEY>:<API_SECRET>@<CLOUD_NAME>`. Verify once with `cld ping` → `{"status": "ok"}`.

---

## Step 1: ANSI → PNG (skip if you already have an image)

```bash
textimg -f ~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf \
        -o <output.png> \
        < <input.ansi>
```

- `-f` — path to the TTF. Required; do not skip.
- `-o` — output PNG path. textimg writes the file, nothing to stdout.
- Input is read from stdin, or pass a positional file argument.

End-to-end from a tmux session:

```bash
tmux capture-pane -t tui-$SID_SHORT -e -p -S - -E - > /tmp/capture.ansi
textimg -f ~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf \
        -o /tmp/capture.png \
        < /tmp/capture.ansi
```

`capture-pane -e` is the key flag — without `-e` the ANSI escapes are stripped and the image will be colorless plain text.

Do **not** rely on textimg's default bundled font. It renders `┌─┐│└┘` with visible gaps between cells and lacks Nerd Font icon glyphs. Use the JetBrainsMono Nerd Font path above.

### Useful textimg flags

| Flag | Effect | When to use |
|---|---|---|
| `-b <hex>` | Background color, e.g. `-b 1e1e2e` | Match a specific terminal theme |
| `-g <WxH>` | Force image size | Rare — defaults follow cell geometry |
| `-s <N>` | Font size in points | Default is fine; bump for very dense TUIs |

### If you plan to annotate: widen the canvas first

textimg sizes the PNG to the widest line of input. If you then want arrows + labels on the right edge (the common case for bug reports), the labels will fall off the image. Pre-extend the canvas before handing to `annotate.md`:

```bash
textimg -f "$FONT" -o /tmp/raw.png < /tmp/capture.ansi
read W H <<< "$(magick identify -format '%w %h' /tmp/raw.png)"
MARGIN=320                                   # room for a line + 25-char label
magick /tmp/raw.png \
  -background '#111111' -gravity west -extent "$((W+MARGIN))x${H}" +gravity \
  /tmp/wide.png
```

`+gravity` resets the gravity state so subsequent `-annotate` calls use `northwest` (top-left) coordinates, which is what the math in `annotate.md` assumes. Skip this step only if your annotations will land *inside* the original content area.

### Composing non-capture content into the render

`textimg` reads ANSI from any source, not just `tmux capture-pane`. For bug reports that need a "fixture summary + actual output" panel, build a composite ANSI buffer with `printf` and render it in one pass:

```bash
{
  printf '\033[1;36m=== Fixture (abbreviated) ===\033[0m\n'
  printf '\033[90massistant:\033[0m  tool_use t1 Read /a\n'
  printf '\033[90m           \033[0m  tool_use t2 Read /b\n'
  printf '\n\033[1;36m=== CLI output ===\033[0m\n'
  transcript /tmp/fixture.jsonl | tail -14
} > /tmp/composite.ansi
textimg -f "$FONT" -o /tmp/composite-raw.png < /tmp/composite.ansi
```

Any SGR escape you can type in a shell (`\033[1;36m` cyan bold, `\033[90m` dim grey, `\033[0m` reset) will render. Same widen-for-annotation recipe applies on the composite output.

---

## Step 2 (optional): annotate

If you want to add arrows, boxes, or text callouts over the PNG, see `annotate.md`. Skip directly to step 3 otherwise — most shares ship the raw capture.

---

## Step 3: verify before uploading

Before running `cld uploader upload`, Read the image with your image tool. Confirm it shows what you intend to claim about it — the right state, the right annotation on the right target, the expected frames in the right order for a GIF.

**Once the URL is in chat, the claim is made.** The user on mobile cannot cheaply re-inspect the artifact; whatever you paste is what they'll reason about. A mislabeled or wrong-content image costs multiple round-trips to correct.

This is `superpowers:verification-before-completion`: evidence before assertions. Skip the verify step only for captures whose correctness is already established (an unmodified `capture-pane` output you're forwarding raw).

Common failures to catch at this step:

- **PNG blank or truncated** — input ANSI was empty (tmux session not rendered yet, wrong pane, race with capture-pane). Re-capture.
- **Box-drawing chars have gaps** — wrong font; not the Nerd Font specified above.
- **Colors missing** — source capture was produced without `-e`, or ANSI was stripped in transit.
- **Nerd Font icons show as `?`** — font installed but wrong variant (the `-Propo` or `-Mono` variants misbehave; use `-Regular`).

---

## Step 4: upload to Cloudinary

### Naming: derive from the Claude session id

Don't invent ad-hoc session labels. Obtain the Claude session id (invoke `get-session-id` if you don't already have it from earlier in the conversation) and derive folder and tag names from it — same identifier used by `tui-session` and `tui-record`.

```bash
SID=<session-uuid-from-get-session-id>     # e.g. 01234567-89ab-cdef-0123-456789abcdef
SID_SHORT=${SID:0:8}                       # 01234567 — short folder segment
```

Cloudinary `public_id`:

```
<YYYY-MM-DD>-<SID_SHORT>/<NNN>-<slug>
```

- `<YYYY-MM-DD>` — today's date in UTC. Use `date -u +%Y-%m-%d`. Useful for date-based cleanup tags.
- `<SID_SHORT>` — first 8 chars of the Claude session id. Groups every artifact from one conversation together in the Media Library.
- `<NNN>` — 3-digit zero-padded counter, starting at `001`, incremented per upload within the session.
- `<slug>` — short kebab-case description of what this specific shot shows (e.g. `initial-render`, `after-j-x8`, `help-modal`).

Tags on every upload: `<YYYY-MM-DD>,<SID_SHORT>,$SID,tui-share`. Include both short and full session id — short for quick folder-matching, full for precise lookup later.

### Determining the next counter

```bash
FOLDER="$(date -u +%Y-%m-%d)-$SID_SHORT"
COUNT=$(cld --verbosity ERROR admin resources type=authenticated prefix="$FOLDER/" max_results=500 2>/dev/null \
        | jq -r '.resources | length')
NEXT=$(printf '%03d' $((COUNT + 1)))
```

For a burst of uploads, cache the count in a shell variable and increment locally.

### The upload command

```bash
URL=$(cld uploader upload <local-path> \
        public_id="$FOLDER/$NEXT-<slug>" \
        asset_folder="$FOLDER" \
        type=authenticated \
        tags="$(date -u +%Y-%m-%d),$SID_SHORT,$SID,tui-share" \
      | jq -r '.secure_url')
echo "$URL"
```

Why two folder params:

- `public_id=<FOLDER>/<NNN>-<slug>` — unique ID + URL path. Slashes produce a folder-like URL structure (`.../<FOLDER>/<NNN>-<slug>.png`).
- `asset_folder=<FOLDER>` — the Media Library browser's folder. Without this, assets file at the root in the console even if `public_id` has slashes.

Set both to the same value.

Paste `$URL` in chat. Done.

---

## Privacy model

- Assets upload as `type=authenticated`. Direct `res.cloudinary.com/.../authenticated/...` URLs without a signature return **401**.
- The `secure_url` you get back includes a signature fragment (`s--XXXXXXXX--`). That signature is what grants access.
- The URL does **not** expire by default.
- Treat the URL like a password for that specific image: anyone with it can view until the image is deleted. Don't forward.
- Works without logging in — signature is URL-based, not cookie-based.

## Cleanup

Automatic cleanup is out of scope. When you want to prune, use tags:

```bash
cld admin delete_resources_by_tag $SID_SHORT        # one conversation (short id)
cld admin delete_resources_by_tag $SID              # one conversation (full id — more precise)
cld admin delete_resources_by_tag <YYYY-MM-DD>      # one day
cld admin delete_resources_by_tag tui-share         # everything shared via this skill
```

## Pitfalls

- **Forgetting `type=authenticated`** — uploads as public. Anyone who guesses the `public_id` can view. Always set `type=authenticated`.
- **Reusing `public_id` across uploads** — replaces the previous asset. Always bump the counter.
- **Spaces or odd chars in `<slug>`** — stick to `[a-z0-9-]`.
- **`cld ping` failing** — `CLOUDINARY_URL` not exported or malformed. Check `cld config`.
- **Free-plan quota** — 25 GB. TUI captures are tiny; `cld admin usage` shows current totals.
- **Piping `cat file | textimg`** works but prefer `< file` — shorter, avoids a useless process.
- **Very tall captures** (hundreds of lines of scrollback) produce very tall PNGs. For mobile chat, cap the capture range on `capture-pane` to the visible pane.
- **textimg uses ANSI only for color** — if the TUI uses a themed palette that resolves only in a specific terminal emulator, rendered colors will be textimg's defaults for those palette indices.
