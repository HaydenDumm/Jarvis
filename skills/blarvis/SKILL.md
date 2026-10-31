---
name: blarvis
description: Build and change things in the user's open Blender scene through the Blarvis MCP tools (mcp__blarvis__*), fast. Use whenever the user asks to model, place, change, save or look at something in Blender, or mentions Blarvis.
---

# Modelling in Blender with Blarvis

The user watches their Blender viewport while you work. Every tool call is a
round trip to Blender, and they wait on each one. Do each request in as few
calls as possible, then say what you did in one short sentence.

## The fast path

1. **Once per conversation, call `blarvis_context`.** It gives Blarvis's rules,
   the project's conventions and palette, the asset library (names and
   attachment notes) and the scene. Don't call it again: tool results report
   what you made and where. Call `scene_info` only if the user changed the scene
   by hand and you need positions.
2. **Plan the whole request, then make one `batch` call.** List the steps from
   the bottom up. Give every piece a short, unique, descriptive name, and use
   `on_top_of` so each piece stands on the one under it. A building is usually a
   single batch.
3. **Use library assets by their exact names** with `add_asset`, in a batch.
   Pieces that belong together (a base, its roof and parapet, a drum's roof and
   windows) share an origin, so give them the same `location`, or the same
   `on_top_of`.
4. **Don't look unless you need to.** `viewport_image` is a slow round trip and
   a lot to read. Use it only when the user asks to see, or after a
   `run_python` script whose result you can't predict. Use it once, not after
   every step.
5. **Fix failures in one go.** If a batch step fails, the result says which step
   and why. Send a new batch with only the corrected step and the steps after it.
6. **`run_python` is the last resort.** Use it only when no tool can do it, in
   one script that does the whole job and prints what it made.

## Building blocks

- `make_box` (with `chamfer` to cut its corners), `make_drum` (a faceted prism,
  one face looking down -Y), `make_ring` (parapets, trims, bands),
  `make_dome` (faceted).
- `add_windows` puts panes on every vertical face of a drum or box. Use
  `per_face` for several across, and `skip_faces` to leave faces bare,
  counting anticlockwise from the front face (0).
- `place_on_top`, `transform`, `duplicate` (radial or linear, with count
  including the original), `join`, `set_material`, `delete`, `rename`.
- `create_test_scene` lays out the project's tiles, footprint and scale model.
  Use it when the user starts a new model.
- `propose_asset` offers a new reusable component to the user, with a name in
  the library's style, a catalog and attachment notes. They name and save it in
  Blender. Offer one only for a component that's genuinely new and reusable.

Sizes are in Blender units. Positions are a piece's foot: its bottom middle.
A drum's `radius` reaches its corners; its faces sit `radius * cos(pi / sides)`
out from the centre.

## Example

"Put a 2x2 base down with a 16-sided drum on top, windows all round, a purple
parapet and a dome" is one batch:

```json
{"steps": [
  {"tool": "add_asset", "input": {"name": "2x2 Base"}},
  {"tool": "add_asset", "input": {"name": "2x2 Roof"}},
  {"tool": "make_drum", "input": {"name": "drum", "sides": 16, "radius": 1.3, "height": 0.62, "material": "ivory", "on_top_of": "2x2 Roof"}},
  {"tool": "add_windows", "input": {"target": "drum", "width": 0.2, "height": 0.18, "bottom": 0.24}},
  {"tool": "make_ring", "input": {"name": "drum_parapet", "sides": 16, "outer_radius": 1.34, "width": 0.1, "height": 0.12, "material": "purple", "on_top_of": "drum"}},
  {"tool": "make_dome", "input": {"name": "dome", "sides": 16, "rings": 3, "radius": 1.15, "rise": 0.6, "material": "purple", "on_top_of": "drum"}}
]}
```

Use the asset names and material keys `blarvis_context` gives for the project;
the ones above are examples.

## When Blender isn't connected

If a call says Blender isn't connected, ask the user to open the Blarvis tab in
Blender's sidebar (N) and click **Connect Claude Code**.
