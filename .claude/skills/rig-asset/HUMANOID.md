# Humanoid skeleton

Use these names and this hierarchy exactly. Together they fill every required slot of Unity's Humanoid avatar and Godot's SkeletonProfileHumanoid.

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
| thigh.L head | the hip socket, about 10% of hip width in from the side |
| shin.L head | the knee pinch, nudged slightly toward the front |
| foot.L head | the ankle, with the tail at the ball of the foot |
| toe.L | ball of the foot to the toe tip |

Add fingers (`finger_index_1.L` … `_3`, and so on) only when the mesh models separate fingers and the tri budget paid for their loops. Otherwise the whole hand weights to `hand.L`.

Test action poses, all in one `rig_test`:

1. Arms down to the sides, then raised overhead.
2. Elbows bent 130°.
3. Knees bent 120° and hips flexed 90°, as in a squat.
4. Spine and chest bent forward 40°, then twisted 45°.
5. Head turned 70° and nodded 40°.
6. Wrists bent 60° and forearms twisted 80°.
