# Jarvis

Model in Blender by telling it what you want. Type or say *"put a 12-sided drum
on top with a window on each face"*, and Claude builds it in your scene while
you watch. Ctrl+Z takes any command back.

Jarvis works from your own asset library: it reuses your components and offers
to save the new ones it makes. It also follows your project's rules (grid
size, palette, style) from a small profile file.

## What you need

- **Blender 4.2 or newer.** Jarvis is developed on Blender 5.2 for Windows.
- **A Claude API key** from [console.anthropic.com](https://console.anthropic.com/)
  (API keys). Requests are billed per use to that account, separately from any
  Claude subscription. Short commands cost very little, but keep an eye on your
  usage page while you try it.
- An internet connection. Voice commands are optional and transcribed on your
  own computer.

## Install

1. Download `jarvis-<version>.zip` from this repository's **Releases** page.
   Don't unzip it.
2. In Blender, open **Edit > Preferences > Get Extensions**. Open the dropdown
   at the top right and choose **Install from Disk...**, then pick the zip.
3. Go to **Add-ons**, find **Jarvis** and expand it:
   - click **Install** next to *Claude SDK*;
   - optionally, click **Install** next to *Voice*. It's a few hundred MB; the
     speech model downloads the first time you talk.
   - paste your API key into **Anthropic API key**. You can leave it empty if
     `ANTHROPIC_API_KEY` is set in your environment.

## Use it

Press **N** in the 3D viewport and open the **Jarvis** tab.

| To | Do |
| --- | --- |
| Type a request | Type in the box and press ▶, or press **Alt+Shift+J** anywhere in the viewport (Enter sends) |
| Talk | Press **Alt+J** (or **Talk**), speak, and press it again |
| Take a command back | **Ctrl+Z** (each command is one undo step) |
| Forget the conversation | The new-file button, or say "new conversation" (the scene stays) |

Things to try:

- *"Create a test scene"*: reference tiles and a footprint to model against
  (instant, no API call). *"Create a 3x3 test scene"* sizes the footprint.
- *"Put a 4 by 4 plinth down, 0.14 tall"*
- *"Put a drum on top with windows on each face"*
- *"Add a purple parapet round the drum, then a faceted dome"*
- *"Put four piers round it"*
- *"Make the drum 12-sided instead"*

**Saving components.** When Jarvis builds something reusable, a **Save this new
component?** box appears with a suggested name, catalog and notes. Edit them and
click **Save component**. It's saved as a Blender asset in
`<asset folder>/<family>_kit.blend`. To see it in the Asset Browser, add the
asset folder under **Edit > Preferences > File Paths > Asset Libraries**.

## Project profiles

Out of the box Jarvis uses generic settings: a 1-unit grid, a simple palette,
and its own asset folder. To fit your project, write a profile and choose it
under **Project profile** in Jarvis's preferences. A profile is a JSON file;
start from [profiles/example.json](profiles/example.json).

| Field | Meaning |
| --- | --- |
| `name` | Your project's name |
| `conventions` | Rules for Claude, one per line: units, style, what to avoid |
| `tile`, `footprint` | Your grid's tile size in Blender units, and a model's default footprint in tiles |
| `road_height` | Optional: the height a platform's top meets the ground at, shown in the test scene |
| `corner_inset` | Optional: models stay inside the corner cut \|x\| + \|y\| <= (width + depth) / 2 - inset |
| `lane_width` | Optional: a lane this wide up to the footprint in the test scene |
| `materials` | Palette: `"key": ["material name", "sRGB hex"]`. Claude picks materials by key |
| `asset_folder` | Your asset libraries, relative to the profile file |
| `default_family` | The library new components go into by default |
| `scale_model` | Optional: `{"file": "x.blend", "object": "name"}`, shown at true size in the test scene |

Paths in a profile are relative to the profile file. Leave out any field to use
its default.

## Good to know

- **What it sends:** each request sends Claude your request, the profile's
  conventions and a short list of your model's objects (names, bounds,
  materials). A conversation's first request also lists your asset library.
- **Scripts:** when no tool fits, Claude may write and run a short Blender
  Python script. Its one-line summary shows in the log, and undo works. Save
  your file before big experiments.
- **Model and speed:** Claude Opus 5.5 at low effort is the default. Sonnet 5.5
  replies faster, and Haiku 5.5 is the fastest and cheapest, fine for simple
  placing. Change these in the preferences.
- **Refusals:** Opus and Sonnet requests use the API's default refusal fallback.
  If a request is ever declined, it's re-run once on Anthropic's recommended
  fallback model.
- **Collections:** Jarvis's pieces go into the *Jarvis model* collection. The
  test scene goes into *Jarvis reference*, which is never saved as an asset.

## Develop

Jarvis is plain Python inside `jarvis/`. To work on it from a clone:

1. In Blender, open **Get Extensions**, open the dropdown at the top right, and
   choose **Repositories > + > Add Local Repository**. Pick this repository's
   folder.
2. Enable Jarvis. Code changes load after you restart Blender, or disable and
   re-enable it.

Two scripts, both needing only Python's standard library and Blender:

- `python build.py` builds `dist/jarvis-<version>.zip`, the file to attach to a
  GitHub release.
- `python tests/run_tests.py` builds Jarvis, installs it into a throwaway Blender
  profile, and runs the headless tests. Your own Blender settings are never
  touched, and the tests never call the API. Add `--profile your.json` to also
  try your profile.

| File | What it does |
| --- | --- |
| `jarvis/__init__.py` | Preferences, the panel, operators, hotkeys, the instant commands |
| `jarvis/agent.py` | The Claude conversation: the tool loop on a worker thread, with tool calls run on Blender's main thread |
| `jarvis/tools.py` | The tools Claude can use (schemas and code) |
| `jarvis/kit.py` | Materials and mesh builders |
| `jarvis/profile.py` | Project profiles |
| `jarvis/library.py`, `jarvis/merge_asset.py` | Listing, appending and saving assets |
| `jarvis/reference.py` | The test scene |
| `jarvis/voice.py` | Recording and offline transcription |
| `jarvis/deps.py` | Installs the Python packages |

## License

GPL-3.0-or-later (see [LICENSE](LICENSE)), as Blender requires of add-ons.
