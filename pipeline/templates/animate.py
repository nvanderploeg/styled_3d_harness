"""Animate stage: the clips named in asset.json `animations`. Runs on the latest texture stage's .blend with
`asset` predefined."""
import animation

# Named poses, shared by the clips that start or end in them. Signs come from build/rig.py's rig_test poses.
STAND = {"upper_arm.L": (0, 0, -60), "upper_arm.R": (0, 0, 60)}
WAVE = {**STAND, "upper_arm.R": (0, 0, -40), "forearm.R": (90, 0, 0)}

# Each key is a whole pose; the clip's `planted` bones are held on every frame.
animation.clip(asset, "wave", [
    (1, STAND),
    (15, WAVE),
    (30, STAND),
])
