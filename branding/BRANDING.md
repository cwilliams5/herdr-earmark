# Earmark branding

**Picked (2026-11-20): the ear tag, in the Copper palette**, in `eartag/`.
The other options are in `alternatives/`.

## The name

- **To earmark something is to set it aside for a later use.** Closing a
  coding-agent tab in Herdr sets its session aside; Earmark keeps it so it
  can be picked up again.
- **An earmark is also the notch a shepherd cuts into a sheep's ear to show
  whose flock it belongs to.** Earmark files each closed session under the
  Herdr workspace it came from, and shows a workspace only its own.
- **Herding is Herdr's world:** the herd of agents, and the shepherd who
  keeps track of them.

It is not a bookmarking tool for files or web pages, and not an earmark in
the budgeting sense.

**Other finalists:**
- Fermata: a held pause that picks up where it stopped; a Claude Code tool
  with that name existed.
- Reprise: French for "resumption"; a common word, less distinctive.
- Herdbook: a herd's permanent record; more a label than a mark.
- Tabled: set aside to take up later; means the opposite in British English.
- Pinfold: a pound for strays; an uncommon word.
- Ingot: a nod to Forge, the Windows tool it partly replaces; an AI tool
  with that name existed.

Also considered: Dogear, Fold, Recess, Attic and Shelf were taken by
session or Herdr tools.

**Avoid in later renames:** none.

## The logo

A livestock ear tag: a round button with a hole, a short neck, and a body
whose bottom edge is cut into a V. The tag is the herding layer (the mark of
which flock a session belongs to), and the V-cut bottom doubles as a
bookmark ribbon's tail (set aside to come back to). It won because it
carries both layers of the name in one simple shape, reads at 16 px, and
looks like nothing else in Herdr's plugin list.

The alternatives:
- `alternatives/eartag-field/`: the same tag in yellow on field green.
  Yellow collides with Herdr's "working" status color in the sidebar.
- `alternatives/eartag-ribbon/`, `alternatives/eartag-sky/`: the tag in red
  and in blue. Both collide with Herdr's status colors (blocked, finished).
- `alternatives/notch-e/`: a lowercase e with the notch cut into its bowl.
  At small sizes the notch reads as an accent (ě), and a letter is the least
  ownable mark.
- `alternatives/ribbon/`: a tab with a bookmark ribbon through it. The tab
  read as a little table, and the ribbon alone is a generic bookmark icon.
- `alternatives/ear/`: a notched sheep's ear. It read as a leaf.
- `alternatives/tabstack/`: a stack of closed tabs, the front one notched. It
  read as a briefcase or an inbox tray.

`alternatives/overview-concepts.png` and `overview-palettes.png` are the
comparison sheets the pick was made from. An earlier ear tag had the notch
in its side; that read as Pac-Man, so the notch moved to the bottom edge.

## Voice

Plain and practical. Windows terms where they help. No hype, no emoji.
"Earmark" in sentences; the lowercase wordmark only as a logo.

Earmark is a Herdr plugin, not an Omarchy one: it works wherever Herdr runs.
Call things by Herdr's names (workspace, tab, pane, agent, session).

## Palette

| Role | Name | Hex |
|---|---|---|
| Background | Charcoal | `#15181D` |
| Accent | Copper | `#E0844A` |
| Highlight | Verdigris | `#6FB6A8` |
| Text | Linen | `#EEE8DF` |
| Accent on light | Deep copper | `#B0582A` |

Contrast: text on background 14.6:1, the accent on background 6.4:1, deep
copper on white 4.9:1.

Copper is the one tag color Herdr doesn't use for agent states (red blocked,
yellow working, green idle, blue finished), so an Earmark mark or badge is
never mistaken for one. Earmark's own popup follows the user's Herdr theme;
this palette is for the logo, the README and the social preview.

## Rules for the logo

- **One color first** (`currentColor`), so it can follow a theme. The accent
  is optional.
- **It reads at 16px.**
- **Drawn as paths:** no fonts needed.
- **`build.py` regenerates everything:** `python3 branding/build.py`.

## Files

```
branding/
  build.py               regenerates every folder below
  BRANDING.md            this file
  eartag/                the pick: icon.svg, icon-color.svg, wordmark.svg,
                         wordmark-color.svg, lockup-dark.svg and lockup-light.svg
                         (the README header), tile.svg (the app tile), preview.png
  alternatives/          every other option, each with its preview.png,
                         plus the two overview sheets
icon.svg                 at the repo root: the app tile
```
