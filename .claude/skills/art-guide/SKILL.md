---
name: art-guide
description: Write or revise an art guide. Use when the user wants the look of a game, a region of it, or a family of assets set down or changed, or when another skill needs a guide that doesn't exist yet.
---

# Art Guide

You write the art direction that makes a game's assets look like one game: a **world**, **zone** or **set** guide in `assets/_art/`. Read `pipeline/ART.md` first; it defines the layers, the format, the json rules and how they merge. The examples in `pipeline/templates/art/` set the depth and tone to match.

## 1. Place it

Run `pipeline/asset art` to list the chains. Choose the layer: a game's whole look is a world guide, a region's mood is a zone guide, and a family of assets built together is a set guide. A guide refines every guide above it, so read each of those with `pipeline/asset art <chain>`. When the request describes a layer above yours that has no guide yet, write that guide first, then come back for yours.

Done when you can name the file you will write, and you have read every guide above it.

## 2. Gather the look

Collect traits for each section of your layer (ART.md, *Format*): what a reviewer would see on an asset that has the look. Take them from the user's words and refs first. For a look that exists outside this repo (a game, a film, a real place), search for descriptions, artist interviews and breakdowns, and note each trait's source. Where the evidence leaves a defining choice open, such as faithful or reimagined, painted or cel-shaded, take the reading the user's words point to and keep the other for the report.

Distil the look into **leading words**: the fewest words that call it to mind.

Done when every section has traits, each traced to the user, a ref or a source, and the leading words fit on one line.

## 3. Write it

Copy the example for your layer to its place in `assets/_art/`, replace its opening paragraph with one saying what this guide covers, and rewrite every section:

- **Leading words first.** The one-line Style, Mood or Set holds them, and every rule below unpacks them.
- **Observable rules.** Each rule names something a reviewer can point at on a review sheet, like "every long edge bows or tapers".
- **State the target.** Phrase each rule as what to do, and pair any guardrail with what to do instead.
- **Measurements in json.** Sizes, angles, ratios and colours live in the json under their section. The prose names the key and says what it looks like on the asset.
- **The highest layer that holds.** A rule true of the whole game goes in the world guide. A lower guide narrows the guides above it or adds to them.
- **Palette as a value ladder.** Order the swatches from dark to light. Go through every shape, wear and motif rule on the chain for the materials that share an edge on one mesh, and declare each pair in `touches`; the check holds every pair `min_zone_contrast` apart. Accents stay few, and what gameplay needs seen takes the clearest rung.
- **One home per decision.** What every piece of a set shares goes in the set guide, so each asset's `brief` holds only what is its own.
- **Refs with a purpose.** Name each ref and what to take from it. Where the user has no images yet, list the refs to gather.

## 4. Check it

Run `pipeline/asset art <chain> --sheet <scratch>/palette.png`, and fix each rejection at its cause. Then:

- **Read the sheet.** Each row is a swatch, dark to light: its shadow, base and lit colour under the chain's painted light, then its luma as grey. The colour columns say the leading words at a glance, and the grey column separates every pair in `touches`.
- **Read every rule as a reviewer.** Point at where it shows on a review sheet. Move each measurement you find in prose into the json, and cut each rule a guide above already makes.

Done when the chain is accepted, the sheet reads as the leading words, and every rule passes the reviewer read.

## 5. Report

Post each guide's path, its one-line leading words, the sheet, and every choice the evidence left open.

## Revising a guide

A changed json rule marks every built stage on the chain `spec changed`. After the edit, run `pipeline/asset verify` on each built stage of every asset whose `art` starts with the chain, and report each stage that reads CHANGED or FAIL.
