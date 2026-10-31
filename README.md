# Blarvis

Model in Blender by chatting with [Claude Code](https://code.claude.com). Ask
*"put a 2x2 base down with a 16-sided drum on top, windows all round and a
dome"*, and Claude Code builds it in your open Blender scene while you watch.
Each change is one undo step.

Blarvis is purely a Claude Code integration. It runs on your Claude plan, with
no API key and no per-request charges. Claude Code builds from your own asset
library, offers to save the new components it makes, and follows your
project's rules (grid, palette, style) from a small profile file. It can look
at your viewport to check its work.

## What you need

- **Blender 4.2 or newer.** Blarvis is developed on Blender 5.2 for Windows.
- **Claude Code** with a Claude plan, in the terminal or in VS Code.
- **Python 3** on your PATH. Claude Code runs Blarvis's small MCP server with it,
  using only Python's standard library.

## Install

1. **The Blender add-on.** Download `blarvis-<version>.zip` from this
   repository's **Releases** page (don't unzip it). In Blender, open **Edit >
   Preferences > Get Extensions**, open the dropdown at the top right, choose
   **Install from Disk...** and pick the zip. Then make sure **Blarvis** is
   ticked under **Add-ons**.
2. **The MCP server**, so Claude Code can reach Blender. Download or clone this
   repository, then run once, with your own path:

   ```
   claude mcp add --transport stdio --scope user blarvis -- python C:\path\to\Blarvis\bridge\blarvis_mcp.py
   ```

   If `claude` isn't found (for example when you only use the VS Code
   extension), use the Claude Code executable that comes with the extension:
   `%USERPROFILE%\.vscode\extensions\anthropic.claude-code-<version>\resources\native-binary\claude.exe`.
3. **The skill** (recommended). It teaches Claude Code the fast way to use
   Blarvis: one context read, then whole requests in one batch. Copy
   `skills/blarvis` into your Claude Code skills folder, `~/.claude/skills/`
   (on Windows, `%USERPROFILE%\.claude\skills\blarvis`).

## Use it

1. In Blender, press **N** and open the **Blarvis** tab. Blarvis connects to
   Claude Code by itself when Blender starts (you can turn this off in its
   preferences); otherwise click **Connect Claude Code**.
2. Start a Claude Code session and ask it to use Blarvis:
   - *"Use Blarvis to create a test scene"*: reference tiles, the footprint and a
     scale model, from your profile. The **Test scene** button in the panel does
     the same.
   - *"Put a 4 by 4 plinth down, 0.14 tall, with a 12-sided drum on top and a
     window on each face"*
   - *"Add a purple parapet round the drum and a faceted dome"*
   - *"Show me the viewport"*
3. Claude Code's actions appear in the Blarvis panel. **Ctrl+Z** takes any of
   them back.

**Voice:** use your system's dictation in Claude Code's input box: **Win+H** on
Windows, or press **Fn** twice on a Mac.

**Saving components.** When Claude Code builds something reusable, a **Save
this new component?** box appears in the Blarvis panel with a suggested name,
catalog and notes. Edit them and click **Save component**. It's saved as a
Blender asset in `<asset folder>/<family>_kit.blend`. To see it in the Asset
Browser, add the asset folder as a library under **Edit > Preferences >
Assets** (in older Blender versions: **File Paths > Asset Libraries**).

## Project profiles

Out of the box Blarvis uses generic settings: a 1-unit grid, a simple palette
and its own asset folder. To fit your project, write a profile and choose it
under **Project profile** in Blarvis's preferences. A profile is a JSON file;
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

- **Only your computer can connect.** The bridge listens on 127.0.0.1 and
  checks a random token. Its address is in `~/.blarvis/bridge.json` while it's
  connected.
- **Scripts:** when no tool fits, Claude Code may run a short Blender Python
  script in your scene. Undo works, but save your file before big experiments.
- **Collections:** pieces go into the *Jarvis model* collection. The test scene
  goes into *Jarvis reference*, which is never saved as an asset.
- Claude Code usage counts toward your Claude plan's limits as usual.

## Develop

Blarvis is plain Python: the add-on is in `blarvis/`, the MCP server in `bridge/`,
and the Claude Code skill in `skills/`. To work on the add-on from a clone:

1. In Blender, open **Get Extensions**, open the dropdown at the top right, and
   choose **Repositories > + > Add Local Repository**.
2. Tick **Custom Directory** and choose this repository's folder, then enable
   Blarvis.

Code changes load when you restart Blender. Two scripts, both needing only
Python's standard library and Blender:

- `python build.py` builds `dist/blarvis-<version>.zip`, the file to attach to a
  GitHub release.
- `python tests/run_tests.py` builds Blarvis, installs it into a throwaway Blender
  profile, and tests the tools, the library and the bridge. It drives the bridge
  through the real MCP server, as Claude Code does. Add `--profile your.json` to
  also try your profile.

| File | What it does |
| --- | --- |
| `blarvis/__init__.py` | Preferences, the panel and its buttons, the save box |
| `blarvis/bridge.py` | The bridge Claude Code connects to, and Blarvis's rules for Claude |
| `blarvis/session.py` | Runs Claude Code's calls on Blender's main thread; the panel's log |
| `blarvis/tools.py` | The tools (schemas and code), including `batch` and `viewport_image` |
| `blarvis/kit.py` | Materials and mesh builders |
| `blarvis/profile.py` | Project profiles |
| `blarvis/library.py`, `blarvis/merge_asset.py` | Listing, appending and saving assets |
| `blarvis/reference.py` | The test scene |
| `bridge/blarvis_mcp.py` | The MCP server Claude Code runs |
| `skills/blarvis/SKILL.md` | The Claude Code skill |

## License

GPL-3.0-or-later (see [LICENSE](LICENSE)), as Blender requires of add-ons.
