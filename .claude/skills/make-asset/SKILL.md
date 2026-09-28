---
name: make-asset
description: Make a game-ready 3D asset end to end, from art guides and spec through each stage to a verified glTF export. Use when the user or another agent wants a 3D asset, prop, character or set of pieces built for a game, rather than one stage of one.
---

# Make Asset

You are the **orchestrator**. The **requester** is whoever asked for the asset: the user, or an agent that invoked this skill. You hold the spec, dispatch each stage to a fresh agent, and judge its result yourself before the next stage starts. The stages' own skills do the work: `model-asset`, `rig-asset`, `texture-base`, `texture-from-reference` and `animate-asset`. Read `pipeline/ASSET.md` first; it defines the asset folder, the stage order and the commands. Then read `pipeline/ART.md`, which defines the art guides every stage follows.

## 1. Guides

Run `pipeline/asset art` to list the chains, and place the request in one: its world, its zone if it has one, and its set if it has one. When the request brings a look, a region or a set that no guide covers yet, write that guide now with the `art-guide` skill. A set always gets a set guide.

Done when `pipeline/asset art <chain>` accepts the chain, and you have posted each new guide's one-line Style, Mood or Set.

## 2. Spec

Run `pipeline/asset new <slug>`, copy any reference images into `refs/`, and write `asset.json` from the request with `art` set to the chain. Take what the request says. Set `budget_class` to the class in `pipeline/asset art <slug>` that fits the asset; it supplies `tri_budget`, `head_tri_budget`, `texture_size` and the class's `limits`. When the guides have no budgets, fill those from ASSET.md's defaults and budget guide.

Ask the requester only about a field that neither the request nor a default can settle: most often whether it needs a rig, what it's for, and its size in the requester's engine. Offer each interpretation as a concrete option with an ASCII plan preview and units. A bare size like "1x2" hides which axis is which, and which piece it applies to. When you can't ask (you run inside an agent with no way to reach the requester), take the reading the request points to and carry it to the report as a judgement call. When the request asks for motion, name its clips in `animations` (ASSET.md, *Animations*); the `animate` stage then follows the textures. Post the finished spec as a short block (brief, art chain, rig, texture mode, tri budget and any head budget, texture size, height, clips), with a plan diagram for anything directional, and continue.

## 3. Run the stages

Take the stages in the order `pipeline/asset status <slug>` lists them, skipping any that already pass. For each one:

1. **Dispatch** a general-purpose `Agent` with this brief:

   > Use the `<skill>` skill (invoke it with the Skill tool) on asset `<slug>` in `<repo path>`. Work until its completion criterion holds. Keep scratch files under `<scratchpad>/<slug>-<stage>/`, and name scripts `<slug>_<purpose>.py` so none shadows a Python module. Change `asset.json` only where the skill says to. Report: the final check output, the review sheet paths, every judgement call you made, each change to `asset.json`, and anything you could not match.

   A fresh agent per stage keeps each stage's attention on its own criterion, and keeps renders out of your context. Without an Agent tool, invoke the stage's skill yourself and keep the same gate.

2. **Gate.** Run `pipeline/asset status <slug>`; the stage must read `pass`. Then read its review sheet and its shots sheet yourself, and judge them against the brief, the refs and the art guides with fresh eyes. Judge the sheets, not the agent's report of them.

3. **Send back or accept.** If the sheet falls short, `SendMessage` the same agent with each specific finding: the tile, what's wrong, and what right looks like. After three rounds on one stage, stop and bring the sheet and the open findings to the requester.

A stage that changes an upstream stage makes the later ones stale. `status` shows this; rebuild those stages in order before continuing.

## Sets

When the request is several pieces that belong together, they share a set guide and code in `assets/_kit/` (ASSET.md, *Sets*).

- **One home per decision.** Everything the pieces share lives in the set guide or the kit. Each piece's `brief` holds only what is its own.
- **Lead first.** Take one lead piece through each stage alone. Its approved code becomes the kit, and every value it settled that the pieces share (a swatch, a kit measurement) moves into the set guide.
- **Then the variants, in parallel.** Each variant stage's brief says: copy the lead's build script unchanged, edit nothing in `_kit`, and report any problem the lead didn't show as a kit problem, with its tile, rather than working around it.
- **One writer.** Only one agent edits `_kit` at a time, and only while no other agent is building from it.
- **Fix the kit, not the piece.** A problem one variant finds in shared code belongs to every piece. Fix it once in the kit, then rebuild every affected piece.
- **Hold approved pieces still.** After any change to `_kit` or a guide, run `pipeline/asset verify` on every approved stage that uses it. A CHANGED stage is rebuilt and reviewed again. If a fix can't keep approved pieces identical, bring the trade-off to the requester with options before applying it.
- **Consistent across the set.** The guides' limits bind every piece, so when the world guide sets no `limits.texel_density_px_per_m` band, the set guide does. At each texture stage, `pipeline/asset compare <stage> <lead> <piece>...` must read CONSISTENT, or you name why each flagged piece differs.

## 4. Export and report

Run `pipeline/asset export <slug>`; it must print `PASS`. Report to the requester:

- the `.glb` path, the textures folder, and each stage's review sheet
- tris, bones, texture size and file size
- every judgement call the stage agents reported, and every gap they could not close
- for a set: the plan diagram of the pieces, and any trait the whole set shares by decision
