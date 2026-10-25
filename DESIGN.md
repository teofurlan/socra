---
name: Socra
description: A local voice tutor and agent console; the browser app is a dark developer console built around a particle field.
colors:
  ground: "#16181b"
  panel: "#1b1e22"
  raise: "#23272c"
  seam: "#2b2f35"
  seam-strong: "#3a3f47"
  label: "#e6e8eb"
  label-2: "#a2a9b2"
  label-3: "#6b727c"
  accent: "#5aa9e6"
  accent-hover: "#74b8ec"
  on-accent: "#0b1a26"
  live: "#98c379"
  listen: "#e06c75"
  warn: "#e5c07b"
  danger: "#e06c75"
  violet: "#c678dd"
  orange: "#d19a66"
  light-ground: "#eef0f3"
  light-panel: "#ffffff"
  light-raise: "#e9ecf0"
  light-seam: "#d9dde3"
  light-seam-strong: "#c3c9d1"
  light-label: "#1b1e22"
  light-label-2: "#535a64"
  light-label-3: "#858c96"
  light-accent: "#1f78c1"
  light-accent-hover: "#1a68a8"
  light-on-accent: "#ffffff"
  light-live: "#3f7d26"
  light-listen: "#c43d4b"
  light-warn: "#8a5d0c"
  light-danger: "#c43d4b"
  light-violet: "#8e3aa8"
  light-orange: "#a65f22"
typography:
  wordmark:
    fontFamily: "Geist Variable, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Geist Variable, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  question:
    fontFamily: "Geist Variable, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 500
    lineHeight: 1.65
  read:
    fontFamily: "Geist Variable, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.65
  ui:
    fontFamily: "Geist Variable, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  small:
    fontFamily: "Geist Variable, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.45
  head:
    fontFamily: "Geist Variable, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    letterSpacing: "0.06em"
    fontFeature: "all-small-caps"
  mono:
    fontFamily: "JetBrains Mono Variable, Cascadia Mono, ui-monospace, Consolas, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    fontFeature: "no-ligatures"
  code:
    fontFamily: "JetBrains Mono Variable, Cascadia Mono, ui-monospace, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.7
    fontFeature: "no-ligatures"
  kbd:
    fontFamily: "JetBrains Mono Variable, Cascadia Mono, ui-monospace, Consolas, monospace"
    fontSize: "0.6875rem"
    fontWeight: 400
rounded:
  xs: "3px"
  sm: "4px"
  md: "6px"
  lg: "8px"
  xl: "12px"
  full: "9999px"
spacing:
  hair: "1px"
  xs: "4px"
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "24px"
  top-bar: "44px"
  panel-head: "34px"
  control: "36px"
  control-compact: "32px"
  control-composer: "40px"
  gutter: "6ch"
components:
  button-key:
    backgroundColor: "transparent"
    textColor: "{colors.label-2}"
    typography: "{typography.ui}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  button-key-hover:
    backgroundColor: "{colors.raise}"
    textColor: "{colors.label}"
  button-key-selected:
    backgroundColor: "color-mix(in srgb, #5aa9e6 12%, transparent)"
    textColor: "{colors.label}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.on-accent}"
  button-primary-disabled:
    backgroundColor: "transparent"
    textColor: "{colors.label-3}"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.danger}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.label-2}"
    typography: "{typography.small}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "26px"
  top-bar:
    backgroundColor: "{colors.ground}"
    height: "44px"
    padding: "0 16px"
  panel-head:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.label-2}"
    typography: "{typography.head}"
    padding: "0 14px"
    height: "34px"
  composer:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.xl}"
    padding: "7px"
    width: "min(calc(100% - 32px), max(55%, 520px), 780px)"
  choice-row:
    backgroundColor: "transparent"
    textColor: "{colors.label-2}"
    typography: "{typography.ui}"
    rounded: "{rounded.xs}"
    padding: "0 1ch"
    height: "36px"
  choice-row-selected:
    backgroundColor: "{colors.raise}"
    textColor: "{colors.label}"
  menu:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.lg}"
    padding: "16px"
    width: "min(22rem, calc(100vw - 1rem))"
  inline-code:
    backgroundColor: "{colors.raise}"
    textColor: "{colors.label}"
    typography: "{typography.mono}"
    rounded: "{rounded.xs}"
    padding: "0 0.35ch"
---

# Design System: Socra

## Overview

**Creative North Star: "The Quiet Console"**

Socra in the browser is a dark developer console that a developer keeps open beside their editor through a long voice session. The frame never moves: a 44px top bar over full-bleed graphite panels separated by 1px seams. What changes is the content inside the panels: the particle field showing who has the floor, one state line, the conversation log at a reading measure, and, when code arrives, a second panel that slides open on the right. The world is calm, dense, and legible from across the desk; colour carries state, not decoration.

The palette is graphite with a single blue accent, and every other hue is borrowed from a code-editor syntax theme: red for the user's turn, blue for Socra speaking, gold for work, green for a live connection. The same hues colour the syntax in the code panel and the particle field, so state, code, and the visualizer read as one material. A light theme renders the same console on paper-white panels with every hue deepened for contrast; it is a full equal, chosen through System, Light, or Dark in settings and applied before first paint.

The browser console rejects the centred voice-assistant chat (speech bubbles, a pill-shaped composer floating on an empty page). It also leaves the terminal-multiplexer costume (box-drawing frames, monospace chrome, status-bar strips) to a future TUI client; the web borrows only the console's habits, such as speaker labels in a prompt-style gutter and a blinking caret, rendered in the sans.

**Key Characteristics:**
- A fixed console frame: top bar, panel headers, 1px seams; contents change, the layout stays put.
- One accent (blue) for the primary action, selection, focus, and Socra's voice.
- State colours drawn from a syntax palette, each paired with a word.
- Geist for words; JetBrains Mono only for code, paths, and figures.
- The particle field as the centrepiece and the only expressive element.
- Flat panels; shadows only on the two floating layers (composer and menu).
- Dark first, with an equal light theme.

## Colors

Graphite neutrals with one blue accent and a small set of syntax-derived state hues; every value has a deeper light-theme counterpart (`light-*`).

### Primary
- **Console Blue** (`accent`; light `light-accent`): the filled primary action (Send, Start, Allow), the selected option's border and bullet, the focus ring, the text caret, the "socra" speaker label, the speaking state, and function calls in code. Hover deepens to `accent-hover`; text on a filled accent uses `on-accent`.

### Secondary
- **Prompt Red** (`listen`): the user's turn. The state lamp blinks in it while listening; the particle field turns red and amber.
- **Build Gold** (`warn`): work in progress: the thinking state, tool calls in the log, pending connection, the permission prompt's border tint, the silence countdown.
- **Live Green** (`live`): a live connection, the "you" speaker label, and strings in code.

### Tertiary
- **Keyword Violet** (`violet`): keywords in code and the mock-driver connection lamp.
- **Number Orange** (`orange`): numbers in code and the warm second hue of the particle palettes.
- **Fault Red** (`danger`): destructive actions (outlined), errors in the log, and a lost connection. It currently shares its value with Prompt Red.

### Neutral
- **Graphite Ground** (`ground`): the page, the top bar, and the conversation panel, which is transparent so the particles show through.
- **Graphite Panel** (`panel`): the code panel, the composer, the settings menu, the permission prompt.
- **Raised Graphite** (`raise`): the one step of elevation: hover fills, the current tab, the selected choice row, inline code.
- **Seam** (`seam`) and **Strong Seam** (`seam-strong`): 1px dividers between regions and control outlines; the strong seam outlines floating layers, `kbd` keys, and the range track.
- **Label** (`label`), **Label 2** (`label-2`), **Label 3** (`label-3`): primary text; secondary text and inactive controls; tertiary facts (line numbers, comments, code pointers, notes, disabled text).

### Named Rules
**The One Accent Rule.** Blue is the only accent. It marks the primary action, the current selection, focus, and Socra's voice, and nothing else. A screen holds at most one filled blue button.

**The Lamp And Word Rule.** A state colour never stands alone: every lamp (a 7px dot) sits beside the word it means ("Connected", "Agent speaking"), so state reads without colour.

**The One Palette Rule.** State, syntax, and particle colours come from the same hues. A new state or token kind takes an existing hue before a new one is introduced.

## Typography

**Display Font:** none; the system has no display face.
**Body Font:** Geist Variable (with Segoe UI Variable Text, Segoe UI, system-ui)
**Label/Mono Font:** JetBrains Mono Variable (with Cascadia Mono, ui-monospace, Consolas), ligatures off

**Character:** a compact, neutral grotesque for everything said, and a monospace reserved for everything that is literally code. The root is 14px; the ramp moves in single-pixel steps, so hierarchy comes from weight and colour more than size.

### Hierarchy
- **Headline** (600, 1.375rem, 1.25, -0.01em): the one title on the agent setup screen.
- **Wordmark** (600, 0.9375rem, -0.01em): "Socra" in the top bar.
- **Question** (500, 1rem, 1.65): the exam question, the largest running text.
- **Read** (400, 0.9375rem, 1.65, max 72ch): the conversation log and the transcript.
- **UI** (400, 0.875rem, 1.5): controls, the composer, the state line, menu rows.
- **Small** (400, 0.8125rem, 1.45): speaker labels, chips, tabs, notes, code pointers.
- **Head** (600, 0.8125rem, 0.06em, all small caps, `label-2`): panel header titles and settings section titles.
- **Mono** (400, 0.8125rem): paths, tool arguments, inline code, the folder chip.
- **Code** (400, 13px, 1.7): the code panel, set in pixels so code stays at reading size against the 14px root.

### Named Rules
**The Two Faces Rule.** Geist sets words; JetBrains Mono sets only code, file paths, tool arguments, and figures, always with ligatures off. Mono never becomes the UI voice.

**The Reading Measure Rule.** Running conversation text is 15px at 1.65 and never wider than 72 characters.

**The Header Not Eyebrow Rule.** Small-caps Head type names a region (a panel header, a settings section). It is never placed as an eyebrow above a headline or a block of content.

## Layout

A full-height shell with two rows: a 44px top bar (wordmark, Exam/Agent tabs, context chips, connection chip, the menu) and the panel area. The panel area is a three-column grid: conversation, a seam, and the code panel. Closed, the template is `1fr 0 0fr`; open, it is `1fr 1px 0.8fr`, which gives the code panel about 44% of the width. The page does not scroll; each panel scrolls inside itself.

The conversation panel places the particle visualizer and centred state line inside a non-scrolling voice stage (`.voice-stage`) above the scroll container (`.shell-scroll`). The question or conversation timeline scrolls independently below it at the 72ch measure with 24px top padding and `clamp(14px, 3vw, 32px)` side padding, while the floating composer and code split layout remain preserved. Conversation entries use a two-column grid: a 6ch right-aligned speaker gutter ("you", "socra", "tool", "error") and the text, separated by 1.5ch, with 12px between entries. The agent setup form uses the same idea with a 3ch step-number gutter at a 60ch measure.

The composer floats centred above the bottom edge at `min(100% - 32px, max(55%, 520px), 780px)` with 28px below it. Under 1024px it spans the panel with one 12px gap to the bottom and both sides. Under 768px the panels stack vertically instead of side by side (code takes `0.7fr` below the conversation) and the particle slot shrinks to 5rem when code is open. Context chips hide below 768px; the phone keeps question progress in the speaker gutter.

Spacing is tight and console-dense: 8px between controls, 10-14px inside headers and buttons, 24px only at the top of a scroll region.

### Named Rules
**The Fixed Frame Rule.** The top bar, panel headers, and seams never move or restyle with content. New content enters a panel; it does not rearrange the frame.

**The Split Rule.** Code opens by animating the grid template along one axis over 520ms with the console ease-out, and the particle canvas follows its slot every frame. Closing reverses it. Reduced motion makes it instant.

## Elevation & Depth

The console is flat. Regions separate by 1px seams and by tone: ground, panel, and one raised step for hover and selection. Panels carry no shadow. In the conversation panel the header stays solid ground while the content area is transparent, anchoring above the non-scrolling voice stage while the timeline scrolls below. Only the two layers that float above the panels cast a shadow, both soft and pulled up under the element (a negative spread), never an offset slab.

### Shadow Vocabulary
- **Dock shadow** (`box-shadow: 0 12px 32px -18px rgb(0 0 0 / 0.55)`): the floating composer.
- **Popover shadow** (`box-shadow: 0 16px 40px -16px rgba(0,0,0,0.45)`): the settings menu.

### Named Rules
**The Seam Not Shadow Rule.** Depth between regions is a 1px seam plus one tonal step. A shadow is allowed only on an element that floats over the panels.

## Shapes

Small, quiet corners and hairline outlines. Choice rows, inline code, and the folder field use 3px; `kbd` keys 4px; buttons, chips, tabs, and the close control 6px; the settings menu and the permission prompt 8px; the composer, the largest floating element, 12px. Lamps, radio bullets, and the range thumb are circles. Outlines are 1px in `seam` or `seam-strong`; an empty folder field is a dashed seam. No pills, no bubbles.

## Components

### Buttons
Flat keys with a hairline outline; one filled primary per view.
- **Shape:** gently squared (6px), 36px tall; 32px in the menu and inline rows; 40px in the composer.
- **Default key:** transparent with a `seam` outline and `label-2` text at UI size, 14px side padding, 8px icon gap.
- **Primary:** filled `accent`, `on-accent` text, weight 600. Disabled, it drops to the default outline with `label-3` text rather than a faded fill.
- **Danger:** outlined only: `danger` text and a 45% `danger` border; hover adds a 10% tint. Stop and other destructive actions sit apart from the primary.
- **Selected (segmented toggles in the menu):** `accent` border with a 12% accent fill and `label` text.
- **Hover / Focus:** hover fills `raise` and lifts text to `label`; 150ms colour transitions with the console ease-out. Focus is a 2px outline mixed from the accent, offset 2px, on every control.

### Chips
- **Style:** 26px tall, 6px corners, `seam` outline, `label-2` small text, no fill. Context facts (model, folder, question progress) and the connection status.
- **State:** the connection chip carries a 7px lamp in its state colour; pending states blink the lamp.

### Cards / Containers
- **Panels:** full-bleed regions with a 34px header bar (Head title on the left, facts and actions on the right, 14px padding, `seam` bottom border). No corners, no shadow.
- **Permission prompt:** the one card: 8px corners, `panel` fill, a border mixing `warn` 45% into the seam, 16px padding, a gold shield icon, the tool in mono, the detail in a ground-coloured mono block, Deny then Allow (primary) at the right.

### Inputs / Fields
- **Composer:** a single-line field inside the floating 12px-cornered `panel` shell with a `seam-strong` outline; the outline turns `accent` on focus-within. Send (primary) is always present; Stop (danger) appears beside it while the other side has the floor.
- **Choice list:** replaces native selects. Every option is visible as a 36px row with a hollow 11px ring; the chosen row fills `raise`, sets its label in 600, and fills the ring with a 5px accent dot. Arrow keys move and choose.
- **Range:** a 3px `seam-strong` track with a 14px `label` thumb; the value shows right-aligned in tabular figures.

### Navigation
- **Mode tabs:** "Exam" and "Agent" as small text links in the top bar; the current tab is `label`, weight 600, on a `raise` fill with 6px corners; others are `label-2` and lift to `label` on hover.
- **Settings menu:** a three-dot button opens an 8px-cornered `panel` popover (22rem, 16px padding, 20px between sections) with Head-styled section titles: Theme, Microphone, Turns, Visualizer, Shape, Particle colors.

### Particle Field (signature)
The identity's centrepiece, drawn on a canvas behind the conversation panel. Three looks (Lines by default, Letters, Grid) and two shapes (Sphere, Sound wave). Idle, particles drift loose; with a voice they gather into a rotating sphere or five crossing strands. "By state" colouring follows the conversation in two-hue pairs from the state palette (idle graphite to blue, speaking blue to cyan, listening red to orange, thinking gold to orange), with deeper pairs on the light ground; six fixed palettes (Iris, Aurora, Ember, Glacier, Graphite, Orchid) override it. On the agent setup screen the field rests: smaller (0.6 of the radius), at 0.4 of the speed, in idle grey, as the focal point above the form.

### State Line and Log
One centred line under the particles: a 7px lamp (blinking while listening), the state in UI weight 600, then the turn mode in small `label-2` text, or the silence countdown in `warn`. The log below sets speaker labels in the 6ch gutter in their colour (you green, socra blue, tool gold, error red); replies in `label`, interim text in `label-2`. Code blocks never render in the log: the log keeps a small `label-3` pointer ("code panel · ts · 11 lines") where the block was, and the code opens in the code panel.

### Code Panel
A panel titled "Code" with the language and line count in mono `label-3`, and a 28px close control. Lines are numbered in a right-aligned `label-3` gutter, set in Code type, scroll on both axes inside the panel, and are coloured by token: keywords violet, strings green, numbers orange, calls blue, comments `label-3` italic.

## Do's and Don'ts

### Do:
- **Do** keep the frame fixed: a 44px top bar, 34px panel headers, and 1px seams; change content inside panels only.
- **Do** use `accent` for exactly one filled action per view, plus selection, focus, and Socra's voice.
- **Do** pair every state lamp with its word, and take state colours from the syntax palette.
- **Do** set running conversation text at 15px, line height 1.65, within 72ch.
- **Do** set code, paths, and tool arguments in JetBrains Mono with ligatures off, and everything else in Geist.
- **Do** send code to the code panel and leave a pointer in the log where it was.
- **Do** give every new colour a light-theme counterpart and check both themes.
- **Do** honour reduced motion: the split becomes instant and lamps stop blinking.

### Don't:
- **Don't** put shadows on panels; only the composer and the menu float.
- **Don't** use chat bubbles, pill-shaped composers, or a centred chat column on an empty page.
- **Don't** bring the terminal-multiplexer costume into the browser: no box-drawing frames, ASCII borders, status-bar strips, or monospace UI chrome. That look belongs to the future TUI.
- **Don't** introduce a second accent or a gradient; colour is reserved for state and code.
- **Don't** use small-caps Head type as an eyebrow or kicker above content; it names regions only.
- **Don't** fill destructive buttons; they stay outlined and set apart from the primary.
- **Don't** use native select menus; use the choice list.
