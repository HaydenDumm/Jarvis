# The asset libraries: every .blend in the assets folder (the preferences' asset
# folder, else the profile's, else Jarvis's own; register it as an asset library
# to see it in the Asset Browser), one per family (<family>_kit.blend), sharing
# the folder's catalog file (blender_assets.cats.txt). Jarvis lists their assets with each one's notes,
# appends them into the scene, and saves new components into them: the parts
# are baked into one mesh at its attachment point, marked as an asset with its
# name, catalog and notes, and merged into the family's file by a background
# Blender (merge_asset.py), so the open file is never swapped out.
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import kit, profile

_index: dict = {}  # file path -> (mtime, [asset dicts])


def folder() -> Path:
	prefs = bpy.context.preferences.addons[__package__].preferences
	if prefs.asset_folder:
		return Path(bpy.path.abspath(prefs.asset_folder))
	if profile.current()["asset_folder"]:
		return profile.resolve(profile.current()["asset_folder"])
	return Path(bpy.utils.extension_path_user(__package__, path="assets", create=True))


def default_family() -> str:
	return profile.current().get("default_family") or "my"


def family_file(family: str) -> Path:
	stem = family.strip().lower().replace(" ", "_") or default_family()
	return folder() / (stem + ".blend" if stem.endswith("_kit") else stem + "_kit.blend")


def _read(path: Path) -> list:
	"""The assets in one library file, with their notes (linked in for a moment)."""
	found = []
	with bpy.data.libraries.load(str(path), link=True, assets_only=True) as (source, target):
		target.objects = list(source.objects)
	library = None
	for obj in target.objects:
		if obj is None:
			continue
		library = obj.library
		notes = obj.get("attachment_notes", "") or (obj.asset_data.description if obj.asset_data else "")
		low, high = (kit.world_bounds(obj) or (Vector(), Vector()))
		found.append({"name": obj.name, "family": path.stem, "catalog": obj.asset_data.catalog_simple_name if obj.asset_data else "",
			"notes": notes, "size": [round(high[i] - low[i], 3) for i in range(3)]})
	if library is not None:
		bpy.data.libraries.remove(library)
	return found


def assets(refresh: bool = False) -> list:
	everything = []
	root = folder()
	if not root.is_dir():
		return everything
	for path in sorted(root.glob("*.blend")):
		mtime = path.stat().st_mtime
		cached = _index.get(str(path))
		if refresh or cached is None or cached[0] != mtime:
			try:
				_index[str(path)] = (mtime, _read(path))
			except Exception as error:
				_index[str(path)] = (mtime, [])
				print("Jarvis: could not read", path, error)
		everything.extend(_index[str(path)][1])
	return everything


def append(name: str, family: str = "") -> bpy.types.Object:
	"""Appends the asset `name` (from its family's file, or whichever has it) into the model."""
	candidates = [family_file(family)] if family else []
	candidates += [p for p in sorted(folder().glob("*.blend")) if p not in candidates]
	for path in candidates:
		if not path.is_file():
			continue
		with bpy.data.libraries.load(str(path), link=False, assets_only=True) as (source, target):
			if name not in source.objects:
				continue
			target.objects = [name]
		obj = target.objects[0]
		if obj is None:
			continue
		obj.asset_clear() # (the copy in the model is a part, not another asset)
		kit.link(obj)
		return obj
	raise ValueError("No asset named %r in %s" % (name, folder()))


def _catalog_id(path_in_tree: str) -> str:
	"""The catalog's id, adding it to the folder's catalog file if it's new."""
	cats = folder() / "blender_assets.cats.txt"
	lines = cats.read_text(encoding="utf-8").splitlines() if cats.is_file() else ["VERSION 1", ""]
	for line in lines:
		parts = line.split(":")
		if len(parts) >= 2 and parts[1] == path_in_tree:
			return parts[0]
	new_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "astropolis/" + path_in_tree))
	lines.append("%s:%s:%s" % (new_id, path_in_tree, path_in_tree.replace("/", "-")))
	cats.write_text("\n".join(lines) + "\n", encoding="utf-8")
	return new_id


def save(objects: list, name: str, catalog: str, family: str, notes: str, origin: str = "bottom_center") -> str:
	"""Saves `objects` as one new asset `name`; returns where it went."""
	parts = [o for o in objects if o is not None and o.type == "MESH" and not kit.is_reference(o)]
	if not parts:
		raise ValueError("Nothing to save (only meshes outside the reference scene are saved)")
	folder().mkdir(parents=True, exist_ok=True)
	# One mesh from the parts, as they stand in the world
	bm = bmesh.new()
	materials = []
	depsgraph = bpy.context.evaluated_depsgraph_get()
	for part in parts:
		evaluated = part.evaluated_get(depsgraph)
		mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
		mesh.transform(part.matrix_world)
		before = set(bm.faces)
		bm.from_mesh(mesh)
		for mat in mesh.materials:
			if mat not in materials:
				materials.append(mat)
		for face in set(bm.faces) - before:
			face.material_index = materials.index(mesh.materials[face.material_index]) if mesh.materials else 0
		bpy.data.meshes.remove(mesh)
	# Its origin: the middle of its foot (or the world's origin, or the 3D cursor)
	if origin == "bottom_center":
		low = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
		high = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
		at = Vector(((low.x + high.x) * 0.5, (low.y + high.y) * 0.5, low.z))
	elif origin == "cursor":
		at = bpy.context.scene.cursor.location.copy()
	else:
		at = Vector()
	bmesh.ops.translate(bm, verts=bm.verts, vec=-at)
	mesh = bpy.data.meshes.new(name)
	bm.to_mesh(mesh)
	bm.free()
	for mat in materials:
		mesh.materials.append(mat)
	asset = bpy.data.objects.new(name, mesh)
	asset["attachment_notes"] = notes
	asset.asset_mark()
	asset.asset_data.description = notes
	tree = "/".join(p.strip().title() for p in ((family or default_family()).split("_kit")[0], catalog or "Parts"))
	asset.asset_data.catalog_id = _catalog_id(tree)
	asset.asset_data.author = "Jarvis"
	# Written alone to a temporary file, then merged into the family's library
	temp = Path(tempfile.gettempdir()) / ("jarvis-%s.blend" % uuid.uuid4().hex)
	bpy.data.libraries.write(str(temp), {asset}, fake_user=True)
	bpy.data.objects.remove(asset)
	bpy.data.meshes.remove(mesh)
	target = family_file(family)
	script = Path(__file__).with_name("merge_asset.py")
	process = subprocess.run([bpy.app.binary_path, "-b", "--factory-startup", "--python", str(script), "--",
		str(target), str(temp), name, tree], capture_output=True, text=True)
	try:
		temp.unlink()
	except OSError:
		pass
	if "JARVIS_MERGED" not in process.stdout:
		raise RuntimeError("Saving into %s failed:\n%s" % (target.name, (process.stdout + process.stderr)[-1500:]))
	_index.pop(str(target), None)
	try:
		bpy.ops.asset.library_refresh()
	except Exception:
		pass
	return "%s (%s, catalog %s)" % (name, target.name, tree)
