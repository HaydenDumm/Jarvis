# Blarvis's building blocks, in the project profile's conventions (profile.py):
# its grid, dimensions and palette. A model's origin is the middle of its
# footprint on the ground; Z is up and the front is -Y. Each material is named
# as the profile says, so a game reading surfaces by name or colour maps them.
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import profile

# (their old name: saved in existing .blend files and matched by projects' build scripts)
MODEL_COLLECTION = "Jarvis model"
REFERENCE_COLLECTION = "Jarvis reference"


def tile() -> float:
	return float(profile.current()["tile"])


def road_height() -> float:
	return float(profile.current()["road_height"] or 0.0)


def srgb(hex_colour: str) -> tuple:
	hex_colour = hex_colour.lstrip("#")
	values = [int(hex_colour[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
	return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values) + (1.0,)


def palette() -> dict:
	"""key -> (material name, linear colour), from the profile."""
	return {key: (entry[0], srgb(entry[1])) for key, entry in profile.current()["materials"].items()}


def material(key: str) -> bpy.types.Material:
	"""The palette material for `key` (a palette key, or any material's name)."""
	name, colour = palette().get(key, (key, None))
	found = bpy.data.materials.get(name)
	if found is not None:
		return found
	made = bpy.data.materials.new(name)
	if colour is None:
		colour = (0.8, 0.8, 0.8, 1.0)
	made.diffuse_color = colour
	try:
		made.use_nodes = True
	except AttributeError:
		pass
	bsdf = made.node_tree.nodes.get("Principled BSDF") if made.node_tree else None
	if bsdf is not None:
		bsdf.inputs["Base Color"].default_value = colour
		bsdf.inputs["Roughness"].default_value = 0.8
	return made


def collection(name: str, reference: bool = False) -> bpy.types.Collection:
	found = bpy.data.collections.get(name)
	if found is None:
		found = bpy.data.collections.new(name)
		bpy.context.scene.collection.children.link(found)
		if reference:
			found["jarvis_reference"] = True # (never saved as an asset)
			found.color_tag = "COLOR_05"
	return found


def link(obj: bpy.types.Object, reference: bool = False) -> bpy.types.Object:
	collection(REFERENCE_COLLECTION if reference else MODEL_COLLECTION, reference).objects.link(obj)
	return obj


def is_reference(obj: bpy.types.Object) -> bool:
	return any(c.get("jarvis_reference") for c in obj.users_collection)


def mesh_object(name: str, build, material_key: str, location=(0.0, 0.0, 0.0), rotation_deg: float = 0.0, reference: bool = False) -> bpy.types.Object:
	"""A flat-shaded object from build(bm), one material, at `location`."""
	bm = bmesh.new()
	build(bm)
	bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
	mesh = bpy.data.meshes.new(name)
	bm.to_mesh(mesh)
	bm.free()
	for poly in mesh.polygons:
		poly.use_smooth = False
	mesh.materials.append(material(material_key))
	obj = bpy.data.objects.new(name, mesh)
	obj.location = location
	obj.rotation_euler = (0.0, 0.0, math.radians(rotation_deg))
	return link(obj, reference)


def box(x0, x1, y0, y1, z0, z1):
	def build(bm):
		v = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
		for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
			bm.faces.new([v[i] for i in f])
	return build


def prism(outline, z0, z1):
	def build(bm):
		low = [bm.verts.new((x, y, z0)) for x, y in outline]
		high = [bm.verts.new((x, y, z1)) for x, y in outline]
		bm.faces.new(low)
		bm.faces.new(high)
		for i in range(len(outline)):
			n = (i + 1) % len(outline)
			bm.faces.new([low[i], low[n], high[n], high[i]])
	return build


def ring_faces(outer, inner, z0, z1):
	"""A band between two closed outlines of the same count (a parapet, a trim)."""
	def build(bm):
		rows = [[bm.verts.new((x, y, z)) for x, y in pts] for pts, z in ((inner, z0), (outer, z0), (outer, z1), (inner, z1))]
		for i in range(len(outer)):
			n = (i + 1) % len(outer)
			for k in range(4):
				m = (k + 1) % 4
				bm.faces.new([rows[k][i], rows[k][n], rows[m][n], rows[m][i]])
	return build


def polygon(sides: int, radius: float, flat_front: bool = True):
	"""A regular polygon's corners, `radius` out to them. With flat_front a face
	looks straight down -Y (the model's front), as the Drum Station's drums do."""
	start = -math.pi / 2 + (math.pi / sides if flat_front else 0.0)
	return [(radius * math.cos(start + math.tau * i / sides), radius * math.sin(start + math.tau * i / sides)) for i in range(sides)]


def chamfered_square(half_x: float, half_y: float, chamfer: float):
	"""A rectangle's outline with its corners cut `chamfer` along each side."""
	c = max(0.0, min(chamfer, half_x, half_y))
	if c <= 0.0:
		return [(half_x, -half_y), (half_x, half_y), (-half_x, half_y), (-half_x, -half_y)]
	return [(half_x - c, -half_y), (half_x, -half_y + c), (half_x, half_y - c), (half_x - c, half_y),
		(-half_x + c, half_y), (-half_x, half_y - c), (-half_x, -half_y + c), (-half_x + c, -half_y)]


def world_bounds(obj: bpy.types.Object):
	"""(low, high) corners of obj in the world, or None for an object with no geometry."""
	if obj.type != "MESH" or not obj.data.vertices:
		corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box] if obj.type in ("MESH", "CURVE", "FONT") else []
		if not corners:
			return None
	else:
		corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
	low = Vector([min(c[i] for c in corners) for i in range(3)])
	high = Vector([max(c[i] for c in corners) for i in range(3)])
	return low, high


def corner_limit(width: float, depth: float):
	"""The corner cut every model stays inside (|x| + |y| at most this), or None."""
	inset = profile.current()["corner_inset"]
	return None if inset is None else (width + depth) / 2.0 - float(inset)


def redraw() -> None:
	for window in bpy.context.window_manager.windows:
		for area in window.screen.areas:
			area.tag_redraw()
