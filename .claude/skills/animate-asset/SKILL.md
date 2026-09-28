---
name: animate-asset
description: Animate a rigged game asset with clips such as idles, sits, emotes and transitions, checked and exported in its glTF. Use when the user or another agent wants an animation, clip or motion made or fixed for a rigged asset.
---

# Animate Asset

You write `build/animate.py`, which keys the clips named in `asset.json` `animations`. Read `pipeline/ASSET.md` first, above all *Animations*; it defines the clip spec, what the check holds, and the commands.

The animate stage builds on the latest texture stage, which builds on the rig. If any of them is failing or stale (`pipeline/asset status <slug>`), bring it back to `pass` first. A clip can't rescue a joint that collapses: that is the rig's fault, and goes back to `rig-asset`.

## 1. Plan the clips

Write `animations` in `asset.json`. For each clip the request names, give:

- **`brief`**: what the body does, in the requester's words plus your reading of them.
- **`frames`** at the spec's `fps`: the action's real duration. A sit or a stand takes 1–1.5 s, standing a little longer than sitting because it lifts the body's weight. An idle loops over 3–6 s.
- **Hand-offs.** A clip that follows another names it in `from`, one that leads into another names it in `to`, and an idle is a `loop`. A set of clips that cycle (stand → sit → idle → stand) closes the cycle with hand-offs.
- **`planted`**: the bones that stay on the ground for the whole clip, usually both feet.

Then add the **props** the performance needs, sized to this character's body rather than to a human's: a seat as high as the thighs sit level with the feet flat on the ground, which is below the knee joint on a thick-limbed character, and a table at its waist. Measure these on the model; the guides' `scale` sizes are for the game's standard character.

Done when every requested clip is in the spec with its frames, hand-offs, planted bones and brief, and every prop the clips touch is in `props`.

## 2. Block the poses

Copy `pipeline/templates/animate.py` to `build/animate.py` and read the docstrings in `pipeline/lib/animation.py`.

- **Read the rig first.** `build/rig.py`'s `rig_test` poses show which axis and sign bend each joint which way, and HUMANOID.md says which way every humanoid joint folds. Take each rotation from there; a guessed sign bends a knee backwards.
- **Named poses.** Write each pose that two clips share (`STAND`, `SEATED`) once, as a named dict, and start or end every clip that meets it on that name. Hand-offs then match by construction.
- **Hips lead.** Move the whole body by the hips bone (`{"loc": ...}` in its local space; for an upright hips bone, local Y is up and local Z is forward), and let `planted` feet hold the legs. For a deep bend, pre-bend the knees and turn the thighs out in the key, so the leg solve starts from knees over the feet. Turn the spine, chest, neck and head to balance over the new support.
- **Contact by `reach`.** A hand resting on a knee or pushing off a seat is placed with `animation.reach`, which lands the wrist on a world point, as `plant` does for feet.
- **Key poses first.** Key the story poses (where each clip starts and ends), then the extremes (the lowest dip, the lean before rising), then the breakdowns that carry the arcs between them.
- **Overlap on top.** `animation.sample` turns the keys into one pose per frame. Add each trailing part's lag from `animation.spring` on the channel it follows, then pass every frame to `clip`.

Keep these rules in view on every clip:

- **Weight over the feet.** Before the hips leave the ground or the seat, the chest leans forward until the head is over the feet. Sitting, the hips reach back and down to the seat and the back straightens only once they land. Standing, the lean comes first and the legs drive up after it.
- **Contact.** A seated body rests on the prop's top: thighs and hips touch it, neither hovering nor sunk in.
- **Overlap.** Parts on chains of their own (a beard, braids, a cloak) trail the body. They start moving 2–4 frames after the bone they hang from, pass its stop, and settle 4–8 frames after it.
- **Ease and spacing.** Keys cluster near the extremes and spread through the fast middle of a move. A heavy body takes longer to stop than to start.
- **A quiet idle.** An idle moves within breathing range: the chest rises 1–3°, the head drifts a few degrees, and hanging parts settle. It shows no new action, and ends on its first pose.

Done when every clip in the spec is keyed through its story poses, extremes and breakdowns.

## 3. Build and review

Run `pipeline/asset build <slug> animate` and fix every `FAIL`. Then read `review/animate.png`, one row per clip, and check each row for:

- **The brief at a glance.** Each frame's silhouette reads as its moment of the action.
- **Contact.** Feet on the ground, and the body on the prop where the brief puts it there.
- **Balance.** No frame where the body would topple: the weight sits over the feet or the seat.
- **Deformation.** No collapsed joint, spike or passing-through. A fault that shows at a joint in every pose belongs to the rig.

Four frames per clip can hide a pop between them. Render more frames of a clip into your scratch space when a move is fast, and step through them.

Done when the check passes and every row reads as its brief.

## 4. Report

Run `pipeline/asset export <slug>` when you own the export; it lists the clips it wrote. Report the review sheet, each clip's frames and hand-offs, the props and their sizes, every judgement call, and any rig fault you found.
