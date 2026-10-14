# Lanes

A lane is one agent, the files it owns, and a checkpoint where you read its sheets.

## Models

Pick each agent's model by the work, and set it on the dispatch. An agent left unset inherits yours.

| model | work | examples |
|---|---|---|
| Haiku | Running tools whose output is fixed by their inputs, and checking the result against a rule | the block-out extract, shape fit, routes map and audit; the placement table; batch reruns; `verify`; export and packing |
| Sonnet | Analysis and construction | a catalogue and plan from the extract; guides; a kit generator and its contract; modelling, materials and bakes; fixes after a send-back |
| Opus (you) | Planning and judgement | questions for the requester; reversible calls; lane order and briefs; reading every sheet at the gate |

- **Haiku's brief names the command and its pass condition.** Write the command line, what a pass looks like and where to write the output. Haiku reports the output and stops. It doesn't redesign a tool that fails: the failure comes back to you.
- **A send-back resumes the same agent, whatever its tier.** A fresh agent reads the kit again before it can fix anything.
- **Move a task up a tier when it fails twice.** Record the move in the plan's decisions, so the next level starts from the right model.

## Brief

Every brief carries this, filled in:

> Use the `make-asset` skill's set rules on set `<set>` in `<repo>`, with `<stage skills>` for the stages. You own `<files>`. Import `<other kits>` and wrap them, never edit them. Keep the signatures of what you own stable, since `<other lane>` imports them.
>
> Decide every reversible choice yourself and list it under **decided** with its reason. Stop only for a change to the gameplay contract or to whether the level can be completed. Defaults announced so far: `<list>`. Each names its fallback, and the guides' rules are the only hard line.
>
> Approved modules are recorded with `pipeline/asset approve`, and a build refuses to change one. When yours is refused, the kit change is the bug.
>
> Keep scratch files in `<scratchpad>/<lane>/` only. Keep `assets/_kit/<set>_notes.md` current (commands, coverage, decisions, frictions): it is the handoff.
>
> Deliver one sheet per class or family showing the module, its variants and every placed instance with materials, from the gameplay camera, plus the contract output and `pipeline/asset status` for every module.
>
> Report: decided, blocked, frictions, and the sheet paths.

Add what the lane needs from the plan:

- its slice of the catalogue
- the failure looks to avoid, naming the built tells (GUIDES.md)
- silhouettes as ratios
- the views it must hold, such as the start and the finish

## Gate

- **Read every sheet yourself.** Judge the sheets, not the report.
- **Hold the start and finish views hardest.** The player sees them first and last.
- **Look for the built tells.** Numbers can't see them. On one level a dyke came out as a brick wall and an arch as a doorway, and both passed every check.
- **Pack after the gate** (DELIVERY.md). Packing finds failures across lanes before the lanes report them.
- **Approve what passes** with `pipeline/asset approve <slug>...`, then commit the lane.

## Send back

- **Name the tile, what's wrong and what right looks like.**
- **Give silhouettes as ratios, not words.** "Krummholz" gave lollipops, then mushrooms. "Trunk visible over at least half the height, pads thinner than a third of their length, sky between the pads" was approved, and the agent turned the ratios into contract checks.
- **Give low-priority pieces a round limit and a cut-off,** such as "if it can't read at this facet size, say so and the set drops it".
- **Stop after three rounds.** After three rounds on one piece without convergence, bring the sheet and the open findings to the requester.

## Running several lanes

- **Shared code.** Shared preview or material code is wrapped, never edited. A shared notes file is split into sections, each with one owner.
- **Scratch folders.** Each lane gets its own scratch folder. Lanes that share one overwrite each other's files, and a cancelled lane should leave one path to delete.
- **Approval snapshots.** A placement or packing lane reads the approval records once per run, since they change while it runs.
- **Starting early.** A lane that depends on another can start before the other's last pieces land. It places pieces still in rework by slug, as `pending`.
- **Usage limits.** When a usage limit stops every lane, resume each from its transcript with "check disk state first, then continue". Batches that rerun safely make this work.
- **Fresh agents.** Once an agent has used about 700k tokens, give its next batch to a fresh agent briefed from the kit's notes file. When the notes are current, that is enough of a handoff.
- **Rigged sets.** `verify` covers bones, clips and vertex colours. Run it on every approved rigged module after a kit change.
