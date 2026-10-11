"""Bake stage of a shared-material asset: the normal and occlusion maps the engine lays over the shared zone
materials, on the low mesh's UVs. Runs with `asset` predefined."""
import bake

bake.detail(asset, ao_distance=0.25)  # metres; give every piece of a set the same distance
