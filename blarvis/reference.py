# "Create a test scene": the project's dimensions to model against, in their own
# collection (Jarvis reference, never saved as an asset), from the profile: a
# field of ground tiles round the origin, the footprint's outline (and, when the
# profile has one, the corner cut every model stays inside), road height, a
# lane up to the footprint's front, and a model at true size for scale.
import math

import bpy

from . import kit, profile


def _tone(name: str, hex_colour: str) -> str:
	"""A reference-only material (not in the palette)."""
	if bpy.data.materials.get(name) is None:
		made = bpy.data.materials.new(name)
		made.diffuse_color = kit.srgb(hex_colour)
		try:
			made.use_nodes = True
			made.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = kit.srgb(hex_colour)
		except (AttributeError, KeyError):
			pass
	return name


def clear() -> None:
	found = bpy.data.collections.get(kit.REFERENCE_COLLECTION)
	if found is None:
		return
	for obj in list(found.objects):
		bpy.data.objects.remove(obj)


def _edge(name: str, p0, p1, z: float, material: str, thickness: float = 0.015) -> None:
	length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
	kit.mesh_object(name, kit.box(-length / 2, length / 2, -thickness, thickness, 0.0, 0.01), material,
		((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, z), math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])), reference=True)


def build(tiles: int = 6, footprint_x: int = 0, footprint_y: int = 0) -> str:
	clear()
	settings = profile.current()
	size = kit.tile()
	footprint_x = int(footprint_x or settings["footprint"][0])
	footprint_y = int(footprint_y or settings["footprint"][1])
	tiles = max(footprint_x + 2, footprint_y + 2, min(int(tiles), 24))
	a, b = _tone("reference_tile_a", "6aa57f"), _tone("reference_tile_b", "4f8a68")
	line, road = _tone("reference_line", "dc6657"), _tone("reference_road", "eee6ce")
	width, depth = footprint_x * size, footprint_y * size
	gap = size * 0.005
	# The ground: tiles round the footprint (an odd footprint centres on a tile)
	start_x = -(tiles * size) / 2.0 + (size / 2.0 if (tiles - footprint_x) % 2 else 0.0)
	start_y = -(tiles * size) / 2.0 + (size / 2.0 if (tiles - footprint_y) % 2 else 0.0)
	for i in range(tiles):
		for j in range(tiles):
			x0, y0 = start_x + i * size, start_y + j * size
			kit.mesh_object("tile_%d_%d" % (i, j), kit.box(x0 + gap, x0 + size - gap, y0 + gap, y0 + size - gap, -size * 0.03, 0.0),
				a if (i + j) % 2 == 0 else b, reference=True)
	# The footprint's outline, and the corner cut inside it
	hx, hy = width / 2.0, depth / 2.0
	outline = [(hx, -hy), (hx, hy), (-hx, hy), (-hx, -hy)]
	for k in range(4):
		_edge("footprint_edge_%d" % k, outline[k], outline[(k + 1) % 4], 0.0, line)
	limit = kit.corner_limit(width, depth)
	notes = ["%dx%d tiles of %g" % (tiles, tiles, size), "a %dx%d footprint" % (footprint_x, footprint_y)]
	if limit is not None:
		for sx in (-1, 1):
			for sy in (-1, 1):
				_edge("corner_cut_%d_%d" % (sx, sy), (sx * hx, sy * (limit - hx)), (sx * (limit - hy), sy * hy), 0.0, line, 0.02)
		notes.append("corner cut |x|+|y| <= %.2f" % limit)
	rise = kit.road_height()
	if rise > 0.0:
		guide = kit.mesh_object("road_height_guide", kit.ring_faces(kit.chamfered_square(hx + 0.04, hy + 0.04, 0.0),
			kit.chamfered_square(hx, hy, 0.0), rise - 0.005, rise), line, reference=True)
		guide.display_type = "WIRE"
		notes.append("road height %g" % rise)
	lane = float(settings["lane_width"] or 0.0)
	front = -hx + size / 2.0 # the middle of the front's first tile
	if lane > 0.0:
		kit.mesh_object("lane", kit.box(front - lane / 2, front + lane / 2, start_y, -hy, max(rise, 0.001) - 0.02, max(rise, 0.001)), road, reference=True)
		notes.append("a lane %g wide" % lane)
	if _scale_model((front + lane * 0.27, -hy - size * 0.7, rise)):
		notes.append("the scale model")
	label = bpy.data.curves.new("label", "FONT")
	label.body = ", ".join(notes)
	label.size = size * 0.15
	text = bpy.data.objects.new("label", label)
	text.location = (start_x, start_y - size * 0.3, 0.0)
	kit.link(text, reference=True)
	return "Test scene: " + ", ".join(notes)


def _scale_model(at: tuple) -> bool:
	"""The profile's scale model (a hovercraft, a figure) at true size, if it has one."""
	model = profile.current().get("scale_model")
	if not model:
		return False
	path = profile.resolve(model["file"])
	if not path.is_file():
		return False
	with bpy.data.libraries.load(str(path), link=False) as (source, target):
		target.objects = [n for n in source.objects if n == model.get("object")] or list(source.objects)[:1]
	obj = target.objects[0] if target.objects else None
	if obj is None:
		return False
	kit.link(obj, reference=True)
	obj.location = at
	return True
