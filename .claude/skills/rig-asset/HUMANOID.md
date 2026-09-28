# Humanoid skeleton

The required bones below fill every required slot of Unity's Humanoid avatar and Godot's SkeletonProfileHumanoid. Use their names and hierarchy exactly; add extra chains under them only as *Extra bones* allows.

## Rest pose

The character faces −Y. Build the rig in the pose the model was made in: an A-pose, arms about 45° below horizontal, unless the request or a guide names a T-pose, arms straight out along ±X. The joint table holds in both.

```
root                         head (0,0,0), tail straight up 10% of height, deform False
└─ hips                      pelvis centre, tail up to the navel
   ├─ spine → chest → neck → head
   │  ├─ shoulder.L → upper_arm.L → forearm.L → hand.L
   │  └─ (mirrored .R)
   ├─ thigh.L → shin.L → foot.L → toe.L
   └─ (mirrored .R)
```

`shoulder.L` is the clavicle and is parented to `chest`. Each chain's bones connect head to tail, and the joints land at:

| joint | where |
|---|---|
| hips | height of the hip sockets, centred |
| chest | bottom of the ribcage |
| neck | base of the neck, just above the shoulder line |
| head | the jaw hinge, just below the ears |
| shoulder.L head | the pit of the neck, 20% of the way toward the arm |
| upper_arm.L head | centre of the shoulder ball |
| forearm.L head | the elbow pinch, nudged slightly toward the back of the arm |
| hand.L head | the wrist pinch |
| thigh.L head | the hip socket, about 10% of hip width in from the side, measured on the legs' own section under any skirt or coat |
| shin.L head | the knee pinch, nudged slightly toward the front |
| foot.L head | the ankle, with the tail at the ball of the foot |
| toe.L | ball of the foot to the toe tip |

Add fingers (`finger_index_1.L` … `_3`, and so on) only when the mesh models separate fingers and the tri budget paid for their loops. Otherwise the whole hand weights to `hand.L`.

## Extra bones

Give a part its own chain when it hangs or trails off the body and would shear, stretch or pass through the body if it followed the required bones: a long beard crossing the neck, a witch's hat tip, a cloak, braids, a tail, long ears. Any skirt, tunic or coat hem that reaches below the hip sockets takes at least a front and a back chain; weighted to `hips` alone, it cuts into the thighs and the seat when the legs lift. A part that rides solid on one bone (a helmet, a shoulder plate) takes `rigid` weights on that bone instead.

- **Where.** Parent each chain's first bone to the bone the part hangs from: a beard or hat to `head`, a cloak to `chest`, a skirt or tail to `hips`, and a braid hanging off a beard to the beard bone it leaves from. The required hierarchy stays untouched, so engines map the humanoid as before and carry the extra chains along for spring or cloth motion.
- **Shape.** Two to four connected bones from the attachment to the tip, along the part's centreline. Name them `<part>_1`, `<part>_2`, … from the root; a pair on both sides takes `.L` and mirrors.
- **Weights.** Pass every extra bone to `rigging.bind` in `skip`, so bone heat leaves them off the body, then `rigging.chain` blends the part along its bones and into the parent at the root.
- **Budget.** Extra bones count toward `limits.max_bones`.

Test action poses, all in one `rig_test`. Directions are in world space, so they read the same from either rest pose:

1. Arms down to the sides, then raised overhead.
2. Elbows bent 130°.
3. Knees bent 120° and hips flexed 90°, as in a squat.
4. Spine and chest bent forward 20° each (40° in all), then twisted 45° in all.
5. Head turned 70° and nodded 40°.
6. Wrists bent 60° and forearms twisted 80°.
7. Each extra chain in poses of its own: all its bones turned together 40° away from the body, then 40° to each side. A chain that hangs free also swings 40° toward the body.

Elbows fold the forearm toward −Y, knees fold the shin toward +Y, and a squat takes the thighs toward −Y. A bend that goes another way has the wrong roll.
