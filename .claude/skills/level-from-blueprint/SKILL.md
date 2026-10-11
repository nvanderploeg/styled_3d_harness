---
name: level-from-blueprint
description: Build every art asset of a game level from a level designer's package (a block-out, route plans, art direction and reference images) as modules fitted to the block-out, placement tables and an engine-ready delivery. Use when the user hands over a block-out or level package and wants the level's art made, or one segment of it.
---

# Level From Blueprint

You are the **orchestrator** of a level's art. The **package** is what the level designers hand over: a block-out that is the level's collision, plans of its routes and jumps, an art direction, and reference images. The **requester** is whoever invoked you. You turn the package into art guides, a test article, a catalogue and a build plan, then dispatch the build to lanes of agents and gate every lane yourself. The harness skills do the asset work: `art-guide` writes guides, and `make-asset` with its stage skills builds modules. Read `pipeline/ASSET.md` and `pipeline/ART.md` first.

Two aims bind every step. The art dresses the block-out and never changes what a runner can do. A playtest tweak is a moved, scaled or swapped module, never a remodelled mesh.

## Rules for the whole run

Put these in every brief you write; agents default to deferring.

- **Decide two-way doors.** Make every reversible call yourself (a palette value, a form, a threshold, a dressing family, where a movable backdrop goes, a delivery detail), write it with its reason where it lives (a guide, the plan or a kit's notes), and keep going. Stop only at one-way doors: a change to the gameplay contract or to whether the level can be completed, a destructive action, publishing. Until the test article is approved, checking in is fair. After that, the requester meets your decisions in the report, not as questions.
- **Defaults are preferences with a fallback.** Every default you announce names what happens where it can't be met, and the guides' rules are the only hard line. A default stricter than the world guide with no fallback blocks a lane on a constraint nobody asked for.
- **Announce once, everywhere.** When you settle a default, write it into the guide or plan and send it to every running lane at once, or lanes will settle the same question differently.
- **Approval is data.** `pipeline/asset approve <slug>` records an approved module, and a build that would change it refuses to save. A kit change that trips this is a kit bug: fix the kit, not the module.
- **Lanes own files.** Each lane is the only writer of its files. Others import and wrap them, never edit them. Each lane keeps its scratch in one folder of its own, so a cancelled lane leaves one path to delete.
- **Gate the sheets, not the reports.** Numbers can't see that a wall reads as masonry. Read every sheet yourself, and hold the views the player sees first and last, the start and the finish, hardest.
- **Every batch reruns safely.** A usage limit can stop every lane at once. Approved modules skip and `verify` catches drift, so a lane cut off mid-step resumes with "check disk state first, then continue".
- **References stay internal** unless the package says otherwise. They never enter a zip, a published page or a public repo.

## 1. Discover

Follow [DISCOVERY.md](DISCOVERY.md): read the package, run the tools in `tools/` on the block-out, and audit it.

Done when every fact on DISCOVERY.md's checklist is answered from the package or listed as unknown, the extract, shape fit and routes map exist, the jumps the routes tool pairs agree with the plans, and the audit's findings are listed for the designers.

## 2. Ask once

Some answers can't come from the package. Ask them together, early, each with options, your recommendation and its evidence:

- **Light.** Engine-lit (`texture_mode: "pbr"`, shared tiling materials) or painted light (`"stylized"`). Every material depends on it.
- **Collision.** The block-out stays the collision, with tolerance away from jump lips (recommended for a playtested block-out), or the art carries colliders.
- **Test article.** Two or three candidate pieces: the most typical gameplay piece in open light, the zone's signature form, a plain one.
- **Delivery.** The engine and format. The default is a zip of per-module files, a placement manifest and an engine scene, or an editor script that builds the scene when that engine isn't available here.

When you can't ask, take the recommendations and report them as judgement calls.

## 3. Guides

Write the world guide for the game, a zone guide for the level or segment, and a set guide for its gameplay pieces with the `art-guide` skill, following [GUIDES.md](GUIDES.md). The world guide carries the contract ([CONTRACT.md](CONTRACT.md)).

Done when `pipeline/asset art <chain>` accepts each chain and the palette sheet reads as the leading words.

## 4. Test article

Take the test piece through `make-asset` as the lead of the gameplay set, modular from the start ([MODULES.md](MODULES.md)): a cap class and its body segments, made by a kit generator whose contract runs in code. Have its agent dry-run the generator over the rest of the family. Start step 5 at the same time.

This is the checkpoint you always bring to the requester. Done when they approve the sheets and every value the approval settled is in the guides or the kit.

## 5. Catalogue and plan

Dispatch one agent, read-only on everything but `assets/_plan/`, to write the catalogue and build plan with [PLAN.md](PLAN.md). Gate it: its counts match the block-out, every unfit piece has a provisional design, the direction has filtered the dressing, economies are yes/no items, and questions come in two lists. Decide the economies and every reversible question, and log each call in the plan's decisions.

## 6. Build in lanes

Run the plan's batches with [LANES.md](LANES.md): one lane per set of files, briefed from its template, gated at checkpoints. A typical order is guides for the new sets, then the gameplay classes, then the unfit gameplay pieces and the decor kit, then backdrop and dressing sets in parallel, then dressing placement. Start the delivery lane early ([DELIVERY.md](DELIVERY.md)), and pack after every gate: packing checks every lane against the others.

Done when every set is approved, every placement table passes its contract, and the package has nothing pending.

## 7. Let them look

At each checkpoint, offer a look build: the assembled level in a scene the requester can open (DELIVERY.md, *Look build*). Something viewable now beats something complete later.

## 8. Deliver and report

Build the delivery package with DELIVERY.md, then report:

- the package's path, contents and counts (instances and triangles per layer), and the round trip's worst error
- **decided**: every default and judgement call, and where it is written, so the requester can override it
- **blocked**: what needs an answer
- **for the level designers**: what the block-out itself does that the art can't fix, from the audit and the gates, and every waiver
- each lane's cost in time and tokens, to calibrate the next level
