# Run by Jarvis in a background Blender to add one new asset to a family's
# library file (library.save): opens the library (or starts it), appends the
# asset from the temporary file it was written to, files it in a collection
# named after its catalog, laid out beside the others, and saves.
# blender -b --factory-startup --python merge_asset.py -- <library.blend> <temp.blend> <asset name> <catalog path>
import sys
from pathlib import Path

import bpy

library, temp, name, catalog = sys.argv[sys.argv.index("--") + 1:][:4]
library = Path(library)
if library.is_file():
	bpy.ops.wm.open_mainfile(filepath=str(library))
else:
	bpy.ops.wm.read_factory_settings(use_empty=True)
if bpy.context.mode != "OBJECT":
	bpy.ops.object.mode_set(mode="OBJECT")
with bpy.data.libraries.load(temp, link=False) as (source, target):
	target.objects = [n for n in source.objects if n == name] or list(source.objects)
group_name = catalog.split("/")[-1]
group = bpy.data.collections.get(group_name)
if group is None:
	group = bpy.data.collections.new(group_name)
	bpy.context.scene.collection.children.link(group)
# Beside the assets already in this catalog, so the file reads as a catalogue
column = len(group.objects)
row = list(bpy.context.scene.collection.children).index(group)
for obj in target.objects:
	if obj is None:
		continue
	group.objects.link(obj)
	obj.location = (column * 4.5, row * 4.5, 0.0)
	column += 1
	obj.use_fake_user = False
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(library))
print("JARVIS_MERGED", name, library)
