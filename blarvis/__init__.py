# Blarvis: model in Blender by chatting with Claude Code (README.md). Blarvis is
# purely a Claude Code integration: Claude Code, on your Claude plan, calls
# Blarvis's tools (tools.py) through its MCP server and the bridge Blarvis opens
# on this computer (bridge.py), and builds in the open scene from your asset
# libraries (library.py) in your project profile's conventions (profile.py).
# The sidebar's Blarvis tab (N panel) connects, shows what Claude Code did, makes
# the test scene, and asks you to name new components Claude Code offers to
# save. No API key and no calls to any API.
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import bridge, library, profile, reference, tools
from .session import session


class BlarvisPreferences(bpy.types.AddonPreferences):
	bl_idname = __package__

	connect_on_start: BoolProperty(name="Connect to Claude Code when Blender starts", default=True,
		description="Open the bridge Claude Code uses (this computer only) whenever Blarvis loads")
	profile: StringProperty(name="Project profile", subtype="FILE_PATH",
		description="A JSON file with your project's conventions, grid, palette and asset folder (see profiles/example.json). Empty: generic defaults")
	asset_folder: StringProperty(name="Asset folder", subtype="DIR_PATH",
		description="Where the asset libraries live. Empty: the profile's, else Blarvis's own folder")

	def draw(self, context):
		layout = self.layout
		layout.prop(self, "connect_on_start")
		layout.prop(self, "profile")
		try:
			layout.label(text="Project: %s" % profile.current()["name"])
		except Exception as error:
			layout.label(text="The profile couldn't be read: %s" % error, icon="ERROR")
		layout.prop(self, "asset_folder")
		layout.label(text="Assets: %s" % library.folder())


class BLARVIS_OT_connect(bpy.types.Operator):
	bl_idname = "blarvis.connect"
	bl_label = "Connect Claude Code"
	bl_description = "Let Claude Code build in this scene with Blarvis's tools (only programs on this computer can connect). Press again to disconnect"

	def execute(self, context):
		if bridge.running():
			bridge.stop()
		else:
			bridge.start()
		return {"FINISHED"}


class BLARVIS_OT_test_scene(bpy.types.Operator):
	bl_idname = "blarvis.test_scene"
	bl_label = "Test scene"
	bl_description = "Reference tiles and the footprint (with the corner cut, road height, a lane and a scale model where your profile has them)"
	bl_options = {"REGISTER", "UNDO"}

	def execute(self, context):
		session.log.append(("blarvis", reference.build()))
		return {"FINISHED"}


class BLARVIS_OT_clear_log(bpy.types.Operator):
	bl_idname = "blarvis.clear_log"
	bl_label = "Clear log"
	bl_description = "Clear Blarvis's log (the scene stays)"

	def execute(self, context):
		session.log.clear()
		return {"FINISHED"}


# ---- saving new components ----

def propose(objects, name, catalog, family, notes, origin):
	wm = bpy.context.window_manager
	wm.blarvis_save_objects = ",".join(objects)
	wm.blarvis_save_name = name
	wm.blarvis_save_catalog = catalog
	wm.blarvis_save_family = family or library.default_family()
	wm.blarvis_save_notes = notes
	wm.blarvis_save_origin = origin


class BLARVIS_OT_save_asset(bpy.types.Operator):
	bl_idname = "blarvis.save_asset"
	bl_label = "Save component"
	bl_description = "Save it into the asset library under this name"

	def execute(self, context):
		wm = context.window_manager
		objects = [bpy.data.objects.get(n) for n in wm.blarvis_save_objects.split(",") if n]
		try:
			where = library.save(objects, wm.blarvis_save_name.strip(), wm.blarvis_save_catalog.strip(), wm.blarvis_save_family.strip(),
				wm.blarvis_save_notes.strip(), wm.blarvis_save_origin)
		except Exception as error:
			self.report({"ERROR"}, str(error)[:300])
			return {"CANCELLED"}
		session.log.append(("blarvis", "Saved " + where))
		wm.blarvis_save_objects = ""
		return {"FINISHED"}


class BLARVIS_OT_skip_asset(bpy.types.Operator):
	bl_idname = "blarvis.skip_asset"
	bl_label = "Skip"
	bl_description = "Don't save it"

	def execute(self, context):
		context.window_manager.blarvis_save_objects = ""
		return {"FINISHED"}


# ---- the panel ----

class BLARVIS_PT_panel(bpy.types.Panel):
	bl_space_type = "VIEW_3D"
	bl_region_type = "UI"
	bl_category = "Blarvis"
	bl_label = "Blarvis"

	def draw(self, context):
		layout = self.layout
		wm = context.window_manager
		connected = bridge.running()
		layout.operator("blarvis.connect", text="Connected to Claude Code" if connected else "Connect Claude Code",
			icon="LINKED" if connected else "UNLINKED", depress=connected)
		if connected:
			layout.label(text="Ask Claude Code to use Blarvis", icon="INFO")
		row = layout.row(align=True)
		row.operator("blarvis.test_scene", icon="GRID")
		row.operator("blarvis.clear_log", text="", icon="TRASH")
		try:
			layout.label(text="Project: %s" % profile.current()["name"], icon="PRESET")
		except Exception:
			layout.label(text="The project profile couldn't be read", icon="ERROR")
		if wm.blarvis_save_objects:
			box = layout.box()
			box.label(text="Save this new component?", icon="ASSET_MANAGER")
			box.prop(wm, "blarvis_save_name", text="Name")
			box.prop(wm, "blarvis_save_catalog", text="Catalog")
			box.prop(wm, "blarvis_save_family", text="Family")
			box.prop(wm, "blarvis_save_notes", text="Notes")
			box.prop(wm, "blarvis_save_origin", text="Origin")
			row = box.row()
			row.operator("blarvis.save_asset", icon="CHECKMARK")
			row.operator("blarvis.skip_asset", icon="X")
		if session.log:
			log = layout.box()
			for who, text in session.log[-12:]:
				first = True
				for chunk in _wrap(text, 44):
					log.label(text=chunk, icon={"claude code": "CONSOLE"}.get(who, "LIGHT") if first else "BLANK1")
					first = False


def _wrap(text: str, width: int) -> list:
	lines = []
	for paragraph in text.splitlines() or [""]:
		while len(paragraph) > width:
			cut = paragraph.rfind(" ", 0, width)
			cut = cut if cut > 0 else width
			lines.append(paragraph[:cut])
			paragraph = paragraph[cut:].lstrip()
		lines.append(paragraph)
	return lines[:12]


def _pump():
	return session.pump()


def _connect_on_start():
	addon = bpy.context.preferences.addons.get(__package__)
	if addon is not None and addon.preferences.connect_on_start and not bpy.app.background:
		bridge.start()


CLASSES = (BlarvisPreferences, BLARVIS_OT_connect, BLARVIS_OT_test_scene, BLARVIS_OT_clear_log, BLARVIS_OT_save_asset, BLARVIS_OT_skip_asset, BLARVIS_PT_panel)
SAVE_PROPS = ("blarvis_save_objects", "blarvis_save_name", "blarvis_save_catalog", "blarvis_save_family", "blarvis_save_notes", "blarvis_save_origin")


def register():
	for cls in CLASSES:
		bpy.utils.register_class(cls)
	wm = bpy.types.WindowManager
	wm.blarvis_save_objects = StringProperty()
	wm.blarvis_save_name = StringProperty(name="Name")
	wm.blarvis_save_catalog = StringProperty(name="Catalog")
	wm.blarvis_save_family = StringProperty(name="Family")
	wm.blarvis_save_notes = StringProperty(name="Notes")
	wm.blarvis_save_origin = EnumProperty(name="Origin", items=[("bottom_center", "Bottom middle", ""), ("world_origin", "World origin", ""), ("cursor", "3D cursor", "")])
	tools.propose_hook = propose
	bpy.app.timers.register(_pump, persistent=True)
	bpy.app.timers.register(_connect_on_start, first_interval=1.0)


def unregister():
	bridge.stop()
	if bpy.app.timers.is_registered(_pump):
		bpy.app.timers.unregister(_pump)
	tools.propose_hook = None
	for prop in SAVE_PROPS:
		if hasattr(bpy.types.WindowManager, prop):
			delattr(bpy.types.WindowManager, prop)
	for cls in reversed(CLASSES):
		try:
			bpy.utils.unregister_class(cls)
		except RuntimeError: # (not registered: an update replaced an older version mid-session)
			pass
