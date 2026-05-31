# Annotating an image before sharing

Optional step in the `tui-share` pipeline. Loaded only when you need arrows, boxes, circles, or text callouts over the image before uploading. Uses ImageMagick's `magick` CLI. Works on any image (PNG or GIF), not just TUI captures.

## When to use

- You want to say "look at **this**" visually rather than describe coordinates in prose.
- You want to add a written callout outside the content area that points back at a feature.
- You're preparing a bug-report or demo image where a raw screenshot isn't self-explanatory.

If the raw capture is self-explanatory, skip annotation and go straight to upload.

## The workflow: locate, draw, verify

Skipping any of these steps is how annotations end up pointing at empty sky. Do not share an annotated image until all three are done.

1. **Locate the target in the source ANSI**, not by eyeballing the rendered PNG. Grep for the text or the style marker you want to point at, convert the matched `(col, row)` to pixels via the formula in "Mapping TUI cells to pixels".
2. **Draw** with `magick` using those deterministic coordinates.
3. **Verify** — Read the annotated image and confirm the annotation is on the intended target. If not, iterate. `superpowers:verification-before-completion` applies here: evidence before assertions.

## Prerequisites

- `magick` on PATH. Install: `brew install imagemagick`.
- A font file path for any text labels (ImageMagick has **no default font** on Homebrew macOS — omitting `-font` causes text annotation to fail silently). Reuse `~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf` for consistency with textimg-rendered TUI captures.

## Finding a target in the capture

For a capture from a 120×40 pane saved as `capture.ansi`:

```bash
# 1-based row where "## User" first appears
grep -n '## User' capture.ansi | head -1
# → "26:..."  means row 26

# Find the column a substring starts at on a given row
awk 'NR==26' capture.ansi | sed 's/\x1b\[[0-9;]*m//g' | grep -bo 'token' | head -1
# → "42:token" means col 42 (0-based byte offset after ANSI-stripping)

# Find rows that carry the selection-bg escape (e.g. #333333 = 51,51,51)
grep -n '48;2;51;51;51' capture.ansi | awk -F: '{print $1}'
```

At `cell_w=10`, `cell_h=22`:

```
pixel_x = col * 10
pixel_y = row * 22        # top edge of the cell; add cell_h for bottom
```

For a circle centered on a row, use `y = row * 22 + 11` (mid-cell).

## The command shape

```bash
magick <in.png> \
  <shape or text primitives, in order> \
  <out.png>
```

ImageMagick maintains a persistent "settings" state that every drawing/text primitive reads from. Every setting you pass (`-fill`, `-stroke`, `-strokewidth`, `-font`, `-pointsize`, `-undercolor`, `-gravity`, `-background`, `-density`, ...) persists across subsequent primitives until you change it or reset with `+<name>` (e.g. `+gravity`). Set what you need *immediately before* each `-draw` / `-annotate`; never assume carry-over is what you want.

Geometry operators (`-crop`, `-resize`, `-extent`, `-rotate`) are different — they modify the image in place rather than setting state. But they often ship with a gravity they inherited from an earlier flag; always follow `-extent ... -gravity <dir>` with `+gravity` before annotating if the annotation block assumes the default (northwest / top-left) coordinate origin.

## Primitive recipes

### Rectangle outline (highlight a region)

```bash
-fill none -stroke '#ff3333' -strokewidth 3 \
  -draw "rectangle <x1>,<y1> <x2>,<y2>"
```

Pick `-fill none` so the content underneath stays visible; only the border draws.

### Filled rectangle (mask / redact)

```bash
-fill '#000000' -stroke none \
  -draw "rectangle <x1>,<y1> <x2>,<y2>"
```

### Ellipse / circle

```bash
-fill none -stroke '#ff3333' -strokewidth 3 \
  -draw "ellipse <cx>,<cy> <rx>,<ry> 0,360"
```

`rx` and `ry` are the X and Y radii (set equal for a circle).

### Arrow (line + filled triangle head)

```bash
-fill '#ff3333' -stroke '#ff3333' -strokewidth 3 \
  -draw "line <x1>,<y1> <xtip>,<ytip>" \
  -draw "polygon <xtip>,<ytip> <xbase1>,<ybase1> <xbase2>,<ybase2>"
```

For a left-pointing arrow ending at `(xtip, ytip)` with a 15 px head:

```
base1 = (xtip + 15, ytip - 9)
base2 = (xtip + 15, ytip + 9)
```

Mirror signs for other directions.

### Text label with backdrop (readable over any background)

```bash
-font <path-to-ttf> \
-fill black -undercolor '#ffeb3bdd' -stroke none \
-pointsize 22 -annotate +<x>+<y> ' your text '
```

- `-undercolor` draws a filled rectangle behind the text — critical for readability over busy backgrounds. The `dd` alpha gives a slight transparency.
- Pad the text with spaces inside the quotes (`' your text '`) so the backdrop has breathing room.
- `+<x>+<y>` is the *baseline* of the first character (y increases downward); expect to tweak by the font's descender height.

## Before/after comparisons

For any "here's the bug" + "here's the fix" pair of captures, the captures must be diffed before annotating. Two captures that look subtly different at a glance can be byte-identical in ANSI — in which case whatever change was made did not alter the rendered pane, and claiming a visual fix on top is dishonest.

```bash
diff before.ansi after.ansi | head -80
```

- **Empty diff** → the change didn't affect the pane. Either the change is in a non-visual area (fine — don't claim visual improvement), or the TUI never reloaded the edited source, or captures were at different states. Investigate before annotating.
- **Diff exists** → read it. Confirm the bytes that changed correspond to the improvement intended. Only then annotate the specific changed region.

Annotating regions that did not actually change is the most common failure mode of this workflow.

## Full example (point-and-label)

Red box around a region, red arrow pointing at it from the right, yellow-backed label:

```bash
FONT=~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf
magick in.png \
  -fill none -stroke '#ff3333' -strokewidth 3 \
    -draw "rectangle 22,676 790,712" \
  -fill '#ff3333' -stroke '#ff3333' -strokewidth 3 \
    -draw "line 900,694 808,694" \
    -draw "polygon 808,694 822,685 822,703" \
  -font "$FONT" -fill black -undercolor '#ffeb3bdd' -stroke none \
    -pointsize 22 -annotate +905+702 ' selected row ' \
  out.png
```

## Mapping TUI cells to pixels

When annotating an image produced by textimg (default 20 pt with JetBrainsMono Nerd Font), each terminal cell maps to roughly:

```
cell_w = image_width  / tmux_cols
cell_h = image_height / tmux_rows
```

For a 120×40 pane that renders as 1200×880: `cell_w = 10 px`, `cell_h = 22 px`.

Then a TUI cell `(col, row)` occupies:

```
top-left     = (col * 10,       row * 22)
bottom-right = ((col + 1) * 10, (row + 1) * 22)
```

Use that to turn "cell (col=40, row=32)" into a rectangle at `(400,704)-(410,726)` to highlight exactly one character, or expand x range for a full row.

## Verifying the annotated image

After writing the output, Read it. Check:

- Annotation (arrow tip, circle center, text position) lands on the intended target. If the thumbnail is too small, crop with `magick out.png -crop <WxH>+<X>+<Y> crop.png` and Read the crop.
- Text label is readable against its backdrop (not cut off, not same color as background).
- No annotation overflows image bounds.

**Do not upload or paste the URL in chat until this verification has passed.**

## Inspecting artifacts: when to look vs. when to grep

- **Structural questions** ("what bytes changed", "which rows have which color", "where is the ▶"): grep/diff the ANSI. Vision is overkill and costs ~10× the tokens for an inferior answer.
- **Perceptual questions** ("does the arrow land on target", "does the fix look right"): Read a focused crop, not the full image. A 300×200 crop costs the same as a 1200×880 full image in vision tokens but has higher effective detail density.
- **Zoom** (`-scale 600%`) doesn't improve your own perception — interpolation adds no signal. It *is* worthwhile when the crop is a final demo artifact for the user.

Rule of thumb: for every image you Read, you should already know from ANSI that something worth looking at exists. The image confirms a claim; ANSI produces the claim.

## Pitfalls

- **Silent text failure** — `magick` without `-font` produces the output but drops all `-annotate` calls. No error by default. Always set `-font`.
- **Settings stick** across primitives. See "ImageMagick drawing state" above — every setting flag persists until changed or reset. The most common surprises are: a `-stroke` colour from one `-draw` carrying into the next; a `-gravity` set earlier (often from `-extent`) making `-annotate +X+Y` measure from a different corner than you expected. Re-declare the settings you care about immediately before each drawing/text op; use `+gravity` to reset coordinate origin to top-left.
- **Text baseline quirks** — `-annotate +X+Y` positions the baseline, not top-left. For top-left positioning, add font ascent to Y (roughly `pointsize * 0.75`).
- **Single-invocation preferred** — chain all drawing in one `magick` call rather than piping multiple invocations. Fewer lossy re-encodes, simpler failure surface.
- **GIF inputs** — `magick in.gif ... out.gif` annotates *every frame identically*. To annotate only specific frames, split with `magick in.gif frame_%03d.png`, annotate individually, recombine with `magick -delay <cs> frame_*.png -loop 0 out.gif`.
