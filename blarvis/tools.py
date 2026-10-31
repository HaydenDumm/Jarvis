# Blarvis's tools: what Claude may do in the scene. Each is a JSON-schema
# definition (definitions(), sent with every request in a fixed order so the
# prompt cache holds; its material list is the profile's palette) and a
# function run on Blender's main thread (run), returning a short text result.
# Positions are in Blender units; a piece's "foot" is its bottom middle. New
# pieces go into the "Jarvis model" collection.
import contextlib
import io
import math
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import kit, library, profile, reference

# Set by the UI: called with (object names, name, catalog, family, notes) to
# ask the user to name and save a new component
propose_hook = None


def _object(name: str) -> bpy.types.Object:
	obj = bpy.data.objects.get(name)
	if obj is None:
		raise ValueError("No object named %r" % name)
	return obj


def _objects(names) -> list:
	return [_object(n) for n in (names or [])]


def _xyz(data: dict, key: str, default=(0.0, 0.0, 0.0)) -> Vector:
	value = data.get(key)
	return Vector(value) if value else Vector(default)


def _top_of(name: str) -> Vector:
	low, high = kit.world_bounds(_object(name))
	return Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, high.z))


def _at(data: dict) -> Vector:
	"""Where a new piece's foot goes: on top of an object, or at `location`."""
	if data.get("on_top_of"):
		top = _top_of(data["on_top_of"])
		offset = _xyz(data, "location")
		return Vector((top.x + offset.x, top.y + offset.y, top.z + offset.z))
	return _xyz(data, "location")


def scene_summary(limit: int = 60) -> str:
	"""A compact description of the model for each request."""
	lines = []
	for obj in bpy.context.scene.objects:
		if kit.is_reference(obj) or obj.type not in ("MESH", "EMPTY"):
			continue
		bounds = kit.world_bounds(obj)
		if bounds is None:
			continue
		low, high = bounds
		mats = ",".join(m.name for m in obj.data.materials) if obj.type == "MESH" else ""
		lines.append("%s: x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f [%s]%s" % (obj.name, low.x, high.x, low.y, high.y, low.z, high.z, mats,
			" (selected)" if obj.select_get() else ""))
		if len(lines) >= limit:
			lines.append("... and more (use scene_info)")
			break
	reference_on = bpy.data.collections.get(kit.REFERENCE_COLLECTION) is not None and len(bpy.data.collections[kit.REFERENCE_COLLECTION].objects) > 0
	head = "Scene: %d model objects%s. 3D cursor at %s." % (len(lines), ", reference scene shown" if reference_on else "", tuple(round(c, 2) for c in bpy.context.scene.cursor.location))
	return head + ("\n" + "\n".join(lines) if lines else "")


def _schema(properties: dict, required: list) -> dict:
	return {"type": "object", "properties": properties, "required": required}


_VEC = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
_MAT = {"type": "string", "description": "A palette material key (see the project's palette) or an existing material's name."}
_NAMES = {"type": "array", "items": {"type": "string"}}
_PLACE = {
	"location": dict(_VEC, description="World position of the piece's foot (its bottom middle). With on_top_of, an offset from that object's top middle."),
	"on_top_of": {"type": "string", "description": "Stand the piece on top of this object, centred (location then offsets it)."},
	"rotation_deg": {"type": "number", "description": "Turn about Z, degrees."},
}

_TOOLS = [
	{"name": "create_test_scene", "description": "Show the reference scene: the project's ground tiles, the footprint outline (with its corner cut, road height, a lane and a scale model where the project has them). Replaces any earlier reference scene.",
		"input_schema": _schema({"tiles": {"type": "integer", "description": "Tiles across (default 6)."}, "footprint_x": {"type": "integer", "description": "In tiles (default: the project's)."}, "footprint_y": {"type": "integer"}}, [])},
	{"name": "scene_info", "description": "Every model object with its bounds, materials and selection, and the 3D cursor.", "input_schema": _schema({}, [])},
	{"name": "list_assets", "description": "The asset libraries' components: name, family, catalog, size and attachment notes (where its origin goes).", "input_schema": _schema({}, [])},
	{"name": "add_asset", "description": "Append a library asset into the model. Its origin is its attachment point (see its notes).",
		"input_schema": _schema(dict({"name": {"type": "string"}, "family": {"type": "string", "description": "Its library family, if known."}}, **_PLACE), ["name"])},
	{"name": "make_box", "description": "A box (walls, slabs, decks, piers). Optional chamfered corners.",
		"input_schema": _schema(dict({"name": {"type": "string"}, "size": dict(_VEC, description="Width (X), depth (Y), height (Z)."), "material": _MAT,
			"chamfer": {"type": "number", "description": "Cut each vertical corner this far along each side."}}, **_PLACE), ["name", "size", "material"])},
	{"name": "make_drum", "description": "A faceted drum: a regular prism standing on its foot, one face looking straight down -Y (the front).",
		"input_schema": _schema(dict({"name": {"type": "string"}, "sides": {"type": "integer"}, "radius": {"type": "number", "description": "Out to its corners."},
			"height": {"type": "number"}, "material": _MAT}, **_PLACE), ["name", "sides", "radius", "height", "material"])},
	{"name": "make_ring", "description": "A faceted ring: a parapet, trim or band round a drum or slab (outer radius to its corners, width inward).",
		"input_schema": _schema(dict({"name": {"type": "string"}, "sides": {"type": "integer"}, "outer_radius": {"type": "number"}, "width": {"type": "number"},
			"height": {"type": "number"}, "material": _MAT}, **_PLACE), ["name", "sides", "outer_radius", "width", "height", "material"])},
	{"name": "make_dome", "description": "A faceted dome (flat-shaded rings of facets), its base on its foot.",
		"input_schema": _schema(dict({"name": {"type": "string"}, "sides": {"type": "integer"}, "rings": {"type": "integer"}, "radius": {"type": "number"},
			"rise": {"type": "number"}, "material": _MAT}, **_PLACE), ["name", "sides", "radius", "rise", "material"])},
	{"name": "add_windows", "description": "Window panes on the vertical faces of an object (a drum or box): per_face across each face, at a height above its foot.",
		"input_schema": _schema({"target": {"type": "string"}, "per_face": {"type": "integer"}, "width": {"type": "number"}, "height": {"type": "number"},
			"bottom": {"type": "number", "description": "Pane's bottom, above the target's foot."}, "material": dict(_MAT, description="Default window."),
			"skip_faces": {"type": "array", "items": {"type": "integer"}, "description": "Faces to leave bare, numbered from the front (-Y) round anticlockwise seen from above."},
			"name": {"type": "string"}}, ["target", "width", "height", "bottom"])},
	{"name": "place_on_top", "description": "Stand objects on top of another, centred on it.",
		"input_schema": _schema({"objects": _NAMES, "target": {"type": "string"}}, ["objects", "target"])},
	{"name": "transform", "description": "Move, turn or scale objects. move is relative; location sets the origin.",
		"input_schema": _schema({"objects": _NAMES, "move": _VEC, "location": _VEC, "rotation_deg": {"type": "number"}, "scale": _VEC}, ["objects"])},
	{"name": "set_material", "description": "Give objects one palette material.", "input_schema": _schema({"objects": _NAMES, "material": _MAT}, ["objects", "material"])},
	{"name": "duplicate", "description": "Copies of an object, count in all with the original: in a ring round a centre (radial) or stepped by an offset (linear).",
		"input_schema": _schema({"object": {"type": "string"}, "count": {"type": "integer"}, "mode": {"type": "string", "enum": ["radial", "linear"]},
			"center": _VEC, "offset": _VEC}, ["object", "count", "mode"])},
	{"name": "join", "description": "Join objects into one.", "input_schema": _schema({"objects": _NAMES, "name": {"type": "string"}}, ["objects", "name"])},
	{"name": "delete", "description": "Delete objects.", "input_schema": _schema({"objects": _NAMES}, ["objects"])},
	{"name": "rename", "description": "Rename an object.", "input_schema": _schema({"object": {"type": "string"}, "new_name": {"type": "string"}}, ["object", "new_name"])},
	{"name": "propose_asset", "description": "Ask the user to name and save a new reusable component built in this session into the asset libraries. Suggest a name in the library's style (e.g. \"Medium Drum Parapet\"), a catalog and attachment notes (where its origin goes and what it fits).",
		"input_schema": _schema({"objects": _NAMES, "name": {"type": "string"}, "catalog": {"type": "string", "description": "e.g. Drums, Windows, Roofs, Bases, Entrances, Flags, Foundations."},
			"family": {"type": "string", "description": "Library family (one .blend per family), e.g. civic, housing, props."}, "notes": {"type": "string"},
			"origin": {"type": "string", "enum": ["bottom_center", "world_origin", "cursor"]}}, ["objects", "name", "catalog", "family", "notes"])},
	{"name": "batch", "description": "Run several tool calls in order in one go (one round trip, one undo step): the fastest way to build anything with more than one piece. Later steps can stand on pieces made earlier (on_top_of). Stops at the first failure unless keep_going.",
		"input_schema": _schema({"steps": {"type": "array", "items": {"type": "object", "properties": {"tool": {"type": "string"}, "input": {"type": "object"}}, "required": ["tool", "input"]},
			"description": "Each a tool's name and its input, as you'd call it alone (not batch, viewport_image or run_python)."},
			"keep_going": {"type": "boolean", "description": "Carry on past a failed step."}}, ["steps"])},
	{"name": "viewport_image", "description": "A picture of the 3D viewport as the user sees it, to check your work.",
		"input_schema": _schema({}, [])},
	{"name": "run_python", "description": "Run a Blender Python script when no tool fits (bpy, bmesh, math, Vector, Matrix and the kit helpers are imported: kit.mesh_object, kit.box, kit.prism, kit.ring_faces, kit.polygon, kit.material). Print what it made.",
		"input_schema": _schema({"code": {"type": "string"}, "summary": {"type": "string", "description": "One line: what it does."}}, ["code", "summary"])},
]


_definitions = {"key": None, "tools": None}


def definitions() -> list:
	"""The tool list for the profile in use: the same list (and bytes) every request."""
	palette = sorted(kit.palette())
	key = tuple(palette)
	if _definitions["key"] != key:
		import copy
		made = copy.deepcopy(_TOOLS)
		text = "A palette material key: " + ", ".join(palette) + " (or an existing material's name)."
		for tool in made:
			for prop in tool["input_schema"]["properties"].values():
				if prop.get("description", "").startswith("A palette material key"):
					prop["description"] = text
				elif prop is not None and prop.get("description") == "Default window.":
					prop["description"] = text + " Default window."
		_definitions["key"], _definitions["tools"] = key, made
	return _definitions["tools"]


def _place(obj: bpy.types.Object, data: dict) -> None:
	obj.location = _at(data)
	obj.rotation_euler.z = math.radians(data.get("rotation_deg", 0.0))


def run(name: str, data: dict) -> str:
	handler = globals().get("_tool_" + name)
	if handler is None:
		raise ValueError("Unknown tool %s" % name)
	bpy.context.view_layer.update() # (positions set by an earlier call, measured now)
	result = handler(data)
	bpy.context.view_layer.update()
	kit.redraw()
	return result


def _tool_batch(data):
	lines = []
	for index, step in enumerate(data.get("steps", []), 1):
		name = step.get("tool", "")
		if name in ("batch", "viewport_image", "run_python"):
			lines.append("%d. %s: not in a batch (call it on its own)" % (index, name))
			continue
		try:
			lines.append("%d. %s" % (index, run(name, step.get("input") or {})))
		except Exception as error:
			lines.append("%d. %s failed: %s" % (index, name, error))
			if not data.get("keep_going"):
				lines.append("Stopped; steps after %d didn't run." % index)
				break
	return "\n".join(lines)


def _tool_create_test_scene(data):
	return reference.build(data.get("tiles", 6), data.get("footprint_x", 0), data.get("footprint_y", 0))


def _tool_scene_info(data):
	return scene_summary(limit=400)


def _tool_list_assets(data):
	found = library.assets()
	if not found:
		return "No assets yet in %s" % library.folder()
	return "\n".join("%s [%s / %s] size %s: %s" % (a["name"], a["family"], a["catalog"], a["size"], a["notes"]) for a in found)


def _tool_add_asset(data):
	obj = library.append(data["name"], data.get("family", ""))
	_place(obj, data)
	return "Added %s as %s at %s" % (data["name"], obj.name, tuple(round(c, 3) for c in obj.location))


def _tool_make_box(data):
	sx, sy, sz = data["size"]
	outline = kit.chamfered_square(sx / 2, sy / 2, data.get("chamfer", 0.0))
	obj = kit.mesh_object(data["name"], kit.prism(outline, 0.0, sz), data["material"])
	_place(obj, data)
	return "Made %s" % obj.name


def _tool_make_drum(data):
	outline = kit.polygon(max(3, int(data["sides"])), data["radius"])
	obj = kit.mesh_object(data["name"], kit.prism(outline, 0.0, data["height"]), data["material"])
	_place(obj, data)
	return "Made %s (%d sides, faces %.3f out)" % (obj.name, data["sides"], data["radius"] * math.cos(math.pi / data["sides"]))


def _tool_make_ring(data):
	sides = max(3, int(data["sides"]))
	outer = kit.polygon(sides, data["outer_radius"])
	inner = kit.polygon(sides, max(0.001, data["outer_radius"] - data["width"] / math.cos(math.pi / sides)))
	obj = kit.mesh_object(data["name"], kit.ring_faces(outer, inner, 0.0, data["height"]), data["material"])
	_place(obj, data)
	return "Made %s" % obj.name


def _tool_make_dome(data):
	sides, rings = max(3, int(data["sides"])), max(1, int(data.get("rings", 3)))
	radius, rise = data["radius"], data["rise"]

	def build(bm):
		rows = []
		for k in range(rings):
			angle = (math.pi / 2) * k / rings
			r, z = radius * math.cos(angle), rise * math.sin(angle)
			rows.append([bm.verts.new((x, y, z)) for x, y in kit.polygon(sides, r)])
		top = bm.verts.new((0.0, 0.0, rise))
		for k in range(rings - 1):
			for i in range(sides):
				n = (i + 1) % sides
				bm.faces.new([rows[k][i], rows[k][n], rows[k + 1][n], rows[k + 1][i]])
		for i in range(sides):
			bm.faces.new([rows[-1][i], rows[-1][(i + 1) % sides], top])
		bm.faces.new(list(reversed(rows[0])))
	obj = kit.mesh_object(data["name"], build, data["material"])
	_place(obj, data)
	return "Made %s" % obj.name


def _tool_add_windows(data):
	target = _object(data["target"])
	low, high = kit.world_bounds(target)
	per_face = max(1, int(data.get("per_face", 1)))
	width, height, bottom = data["width"], data["height"], data["bottom"]
	skip = set(data.get("skip_faces", []))
	matrix = target.matrix_world
	centre = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, 0.0))
	faces = []
	for poly in target.data.polygons:
		normal = (matrix.to_3x3() @ poly.normal).normalized()
		if abs(normal.z) > 0.2:
			continue
		corners = [matrix @ target.data.vertices[i].co for i in poly.vertices]
		if max(c.z for c in corners) - min(c.z for c in corners) < bottom + height:
			continue
		faces.append((normal, corners))
	# From the front (-Y) round anticlockwise seen from above
	faces.sort(key=lambda f: (math.atan2(f[0].y, f[0].x) + math.pi / 2) % math.tau)
	panes = []

	def build(bm):
		for index, (normal, corners) in enumerate(faces):
			if index in skip:
				continue
			along = Vector((-normal.y, normal.x, 0.0))
			middle = sum(corners, Vector()) / len(corners)
			span = max(c.dot(along) for c in corners) - min(c.dot(along) for c in corners)
			foot = min(c.z for c in corners)
			for k in range(per_face):
				offset = (k + 0.5) / per_face * span - span / 2
				base = Vector((middle.x, middle.y, foot + bottom)) + along * offset
				for z0, z1 in ((0.0, height),):
					quad = [base + along * (-width / 2) + normal * 0.012, base + along * (width / 2) + normal * 0.012,
						base + along * (width / 2) - normal * 0.012, base + along * (-width / 2) - normal * 0.012]
					low_verts = [bm.verts.new(p + Vector((0, 0, z0))) for p in quad]
					high_verts = [bm.verts.new(p + Vector((0, 0, z1))) for p in quad]
					bm.faces.new(low_verts)
					bm.faces.new(high_verts)
					for i in range(4):
						n = (i + 1) % 4
						bm.faces.new([low_verts[i], low_verts[n], high_verts[n], high_verts[i]])
			panes.append(index)
	name = data.get("name") or target.name + "_windows"
	obj = kit.mesh_object(name, build, data.get("material", "window"))
	return "Made %s: %d panes on %d of %d faces" % (obj.name, len(panes) * per_face, len(panes), len(faces))


def _tool_place_on_top(data):
	top = _top_of(data["target"])
	for obj in _objects(data["objects"]):
		low, high = kit.world_bounds(obj)
		shift = Vector((top.x - (low.x + high.x) / 2, top.y - (low.y + high.y) / 2, top.z - low.z))
		obj.location += shift
	return "Stood %s on %s" % (", ".join(data["objects"]), data["target"])


def _tool_transform(data):
	for obj in _objects(data["objects"]):
		if data.get("location"):
			obj.location = Vector(data["location"])
		if data.get("move"):
			obj.location += Vector(data["move"])
		if "rotation_deg" in data:
			obj.rotation_euler.z = math.radians(data["rotation_deg"])
		if data.get("scale"):
			obj.scale = Vector(data["scale"])
	return "Transformed %s" % ", ".join(data["objects"])


def _tool_set_material(data):
	mat = kit.material(data["material"])
	for obj in _objects(data["objects"]):
		obj.data.materials.clear()
		obj.data.materials.append(mat)
	return "Set %s on %s" % (mat.name, ", ".join(data["objects"]))


def _tool_duplicate(data):
	source = _object(data["object"])
	made = []
	count = max(1, int(data["count"]))
	for k in range(1, count):
		copy = source.copy()
		copy.data = source.data.copy()
		kit.link(copy)
		if data["mode"] == "radial":
			centre = _xyz(data, "center")
			turn = Matrix.Translation(centre) @ Matrix.Rotation(math.tau * k / count, 4, "Z") @ Matrix.Translation(-centre)
			copy.matrix_world = turn @ source.matrix_world
		else:
			copy.location = source.location + _xyz(data, "offset") * k
		made.append(copy.name)
	return "Made %s" % ", ".join(made)


def _tool_join(data):
	parts = [o for o in _objects(data["objects"]) if o.type == "MESH"]
	bm = bmesh.new()
	materials = []
	for part in parts:
		mesh = part.data.copy()
		mesh.transform(part.matrix_world)
		before = set(bm.faces)
		bm.from_mesh(mesh)
		for mat in mesh.materials:
			if mat not in materials:
				materials.append(mat)
		for face in set(bm.faces) - before:
			face.material_index = materials.index(mesh.materials[face.material_index]) if mesh.materials else 0
		bpy.data.meshes.remove(mesh)
	joined = bpy.data.meshes.new(data["name"])
	bm.to_mesh(joined)
	bm.free()
	for mat in materials:
		joined.materials.append(mat)
	for part in parts:
		bpy.data.objects.remove(part)
	obj = kit.link(bpy.data.objects.new(data["name"], joined))
	return "Joined %d objects into %s" % (len(parts), obj.name)


def _tool_delete(data):
	for obj in _objects(data["objects"]):
		bpy.data.objects.remove(obj)
	return "Deleted %s" % ", ".join(data["objects"])


def _tool_rename(data):
	obj = _object(data["object"])
	obj.name = data["new_name"]
	return "Renamed to %s" % obj.name


def _tool_propose_asset(data):
	_objects(data["objects"]) # (they must exist)
	if propose_hook is None:
		return "Saving isn't available"
	propose_hook(data["objects"], data["name"], data["catalog"], data["family"], data["notes"], data.get("origin", "bottom_center"))
	return "Shown to the user to name and save (or skip). Carry on; don't wait for it."


def _tool_viewport_image(data):
	"""The largest 3D viewport, captured and shrunk to at most 1280 across."""
	import base64
	import os
	import tempfile
	areas = [(w, a) for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == "VIEW_3D"]
	if not areas:
		return "There's no 3D viewport to capture (Blender is running without a window)."
	window, area = max(areas, key=lambda wa: wa[1].width * wa[1].height)
	region = next(r for r in area.regions if r.type == "WINDOW")
	path = os.path.join(tempfile.gettempdir(), "blarvis-viewport.png")
	with bpy.context.temp_override(window=window, area=area, region=region):
		bpy.ops.screen.screenshot_area(filepath=path)
	image = bpy.data.images.load(path, check_existing=False)
	try:
		width, height = image.size
		if width > 1280:
			image.scale(1280, max(1, int(height * 1280 / width)))
			image.filepath_raw = path
			image.file_format = "PNG"
			image.save()
	finally:
		bpy.data.images.remove(image)
	with open(path, "rb") as file:
		encoded = base64.b64encode(file.read()).decode("ascii")
	return {"type": "image", "media_type": "image/png", "data": encoded, "note": "The 3D viewport (%s)." % ("rendered" if area.spaces[0].shading.type == "RENDERED" else area.spaces[0].shading.type.lower())}


def _tool_run_python(data):
	output = io.StringIO()
	scope = {"bpy": bpy, "bmesh": bmesh, "math": math, "Vector": Vector, "Matrix": Matrix, "kit": kit}
	try:
		with contextlib.redirect_stdout(output):
			exec(compile(data["code"], "<blarvis>", "exec"), scope)
	except Exception:
		return "Error:\n" + traceback.format_exc(limit=3)[-1500:] + "\nOutput before it:\n" + output.getvalue()[-800:]
	return "Ran: %s\n%s" % (data["summary"], output.getvalue()[-1500:] or "(no output)")
