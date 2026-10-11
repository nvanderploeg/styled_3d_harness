"""Check the level-from-blueprint tools against the package they were lifted from (la montée, paquet-v1).

    python3 test_tools.py [--project .] [--blender ~/opt/blender/blender] [--scratch <dir>]

Plain python3 (numpy). Runs the Blender tools (inventory, extract, piece views) as Blender subprocesses and the
pure ones in this process, writing everything under --scratch (a new temporary folder by default). Run from the
project root, or name it with --project: it reads `paquet-v1/blockout/la-montee.fbx`, the kit's
`assets/_kit/montee_blockout.json` (the extract to match) and `assets/_kit/montee_placement.json` (the cap classes
the level built), and the art guides under `assets/_art/speedrun_academy/`. Prints one line per check and exits 1
on any failure.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plan_geom as pg  # noqa: E402
import routes  # noqa: E402
import shape_fit  # noqa: E402

FBX = "paquet-v1/blockout/la-montee.fbx"
KIT_DATA = "assets/_kit/montee_blockout.json"
PLACEMENT = "assets/_kit/montee_placement.json"
GUIDES = ["assets/_art/speedrun_academy/world_art.md", "assets/_art/speedrun_academy/la_montee/zone_art.md"]
# Classes the level's brief names; the cover proposes the rest around them.
SEEDS = ["hex:10x5:flare", "hex:7.5x5"]
FAILS = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(name)


def blender(exe, script, *args):
    t = time.time()
    run = subprocess.run([exe, "--background", "--factory-startup", "--python", os.path.join(HERE, script), "--",
                          *args], capture_output=True, text=True)
    if run.returncode != 0 or "Traceback" in run.stderr + run.stdout:
        print(run.stdout[-3000:], run.stderr[-3000:])
        raise SystemExit(f"{script} failed")
    return run.stdout, time.time() - t


def test_inventory(a, out):
    _, dt = blender(a.blender, "blockout_inventory.py", a.fbx, out)
    inv = pg.load(out)
    meshes = [o for o in inv["objects"] if o["type"] == "MESH"]
    check("inventory: 53 objects, 43 meshes, 3330 tris (README: 3,330)",
          (len(inv["objects"]), len(meshes), sum(m["tris"] for m in meshes)) == (53, 43, 3330),
          f"{len(inv['objects'])} objects, {len(meshes)} meshes, {sum(m['tris'] for m in meshes)} tris, {dt:.1f} s")
    colours = inv["colour_layers"].get("Col", {}).get("colours", {})
    check("inventory: the four lip colours on Col",
          all(c in colours for c in ("(0.10, 0.35, 1.00)", "(0.00, 0.85, 0.95)", "(0.15, 0.85, 0.15)",
                                     "(1.00, 0.55, 0.00)")))


def test_extract(a, out):
    _, dt = blender(a.blender, "blockout_extract.py", a.fbx, out, "--water", "13.0")
    new = pg.load(out)
    ref = pg.load(a.kit_data)["pieces"]
    game = {k: v for k, v in new["pieces"].items() if v["role"] == "gameplay"}
    check("extract: the gameplay pieces are the kit's", sorted(game) == sorted(ref),
          f"{len(game)} vs {len(ref)}, {dt:.1f} s")
    diffs = [f"{k}.{f}" for k, r in ref.items() for f, v in r.items() if k in game and game[k].get(f) != v]
    check("extract: every field of every gameplay piece matches montee_blockout.json", not diffs,
          ", ".join(diffs[:8]))
    decor = sorted(k for k, v in new["pieces"].items() if v["role"] == "decor")
    check("extract: decor pieces", decor == ["champ_c1", "paroi_c2", "paroi_c3"], ", ".join(decor))
    lips = sorted(c["nearest"] for c in new["lip_colours"] if c["lip"])
    check("extract: lip clusters", lips == ["blue", "cyan", "green", "orange"], ", ".join(lips))


def test_shape_fit(a, extract):
    plain = shape_fit.main([extract, "--out", os.path.join(a.scratch, "fit.json")])
    tops = list(plain["tops"].values())
    shapes = {s: sum(1 for t in tops if t["flat"] and t["shape"] == s) for s in ("rect", "hex", "pent", "weld")}
    check("shape_fit: 43 flat tops: 18 rect, 21 hex, 2 pent, 2 weld",
          sum(t["flat"] for t in tops) == 43 and shapes == {"rect": 18, "hex": 21, "pent": 2, "weld": 2}, str(shapes))
    small = sorted(t["key"] for t in tops if t["status"] == "small")
    check("shape_fit: the lookout's three frame tops are small", small == ["sol_35#1", "sol_35#2", "sol_35#3"])
    check("shape_fit: 8 slopes, all flows, in 5 groups",
          sum(1 for t in tops if t["shape"] == "flow") == 8 and len(plain["flows"]) == 5)
    fitted = sum(1 for t in tops if t["status"] == "fit")
    check("shape_fit: unseeded cover: 10 classes by shape, 15 by shape and flare, over 38 tops",
          fitted == 38 and len(plain["cover"]["shape"]) == 10 and len(plain["cover"]["shape_flare"]) == 15)
    same = {tuple(c) for c in plain["same"]}
    check("shape_fit: identical pairs", {("sol_13", "sol_16"), ("sol_15", "sol_17"), ("sol_1", "sol_35#0")} <= same)
    seeded = shape_fit.main([extract, "--out", os.path.join(a.scratch, "fit_seeded.json")]
                            + [x for s in SEEDS for x in ("--seed", s)])
    if os.path.exists(a.placement):
        built = {tuple(sorted(c["serves"])) for c in pg.load(a.placement)["classes"].values()
                 if c["shape"] in ("rect", "hex", "pent") and c["cap"]}
        mine = {tuple(c["members"]) for c in seeded["cover"]["shape_flare"]}
        check("shape_fit: seeded cover has the level's 15 cap classes, member for member", mine == built,
              f"{len(mine)} vs {len(built)}")


def test_routes(a, extract):
    rt = routes.main([extract, "--out", os.path.join(a.scratch, "routes.json"), "--map",
                      os.path.join(a.scratch, "routes_map.png"), "--start", "sol_1"] + [x for g in a.guides for x in ("--world-guide", g)])
    check("routes: 48 tops, 102 lips, 52 jumps, none unpaired, 3 left out",
          (len(rt.tops), len(rt.lips), len(rt.jumps), len(rt.unpaired), len(rt.left_out)) == (48, 102, 52, 0, 3))
    bad = []
    for j in rt.jumps:
        ends = np.array([rt.lips[i][k][:2] for i in j["lips"] for k in ("a", "b")])
        if pg.signed_dist(ends, j["gap"]).max() > 1e-6:
            bad.append(j["name"])
    check("routes: every jump's gap corridor holds both its lips", not bad, ", ".join(bad))
    check("routes: every jump takes off where its first lip is",
          all(rt.lips[j["lips"][0]]["top"] == j["from"] for j in rt.jumps))
    check("routes: the start's jump runs from it", any(j["from"] == "sol_1#0" for j in rt.jumps))
    check("routes: rules read from the guides", rt.p["gap_clear_m"] == 2.0 and rt.p["approach_m"] == 15.0
          and rt.p["reach_m"] == 12.5 and rt.p["reach_up_m"] == 3.0)
    kit = os.path.join(a.project, "assets", "_kit")
    if os.path.exists(os.path.join(kit, "cliff_routes.py")):
        sys.path.insert(0, kit)
        import cliff_routes
        old = cliff_routes.Routes(a.kit_data, {"gap_clear_m": 2.0, "approach_m": 15.0},
                                  {"reach_m": 12.5, "reach_up_m": 3.0})
        pts = np.random.default_rng(1).uniform([-120, -60, 10], [110, 80, 50], (500, 3))
        same = ({frozenset(j["lips"]): (round(j["gap_m"], 6), j["difficulty"]) for j in old.jumps}
                == {frozenset(j["lips"]): (round(j["gap_m"], 6), j["difficulty"]) for j in rt.jumps})
        check("routes: the kit's cliff_routes pairs the same jumps and answers the same queries",
              same and (old.reach(pts) == rt.reach(pts)).all()
              and np.allclose(old.envelope_dist(pts), rt.envelope_dist(pts))
              and np.allclose(old.corridor_dist(pts), rt.gap_dist(pts)))


def test_piece_views(a, extract):
    outdir = os.path.join(a.scratch, "views")
    _, dt = blender(a.blender, "piece_views.py", a.fbx, extract, "sol_1", outdir, "--routes",
                    os.path.join(a.scratch, "routes.json"))
    files = [os.path.join(outdir, f"sol_1_{v}.png") for v in ("overview", "water", "gameplay")]
    sizes = [os.path.getsize(f) if os.path.exists(f) else 0 for f in files]
    heads = [open(f, "rb").read(8) if os.path.exists(f) else b"" for f in files]
    check("piece_views: three non-empty PNGs for sol_1",
          all(s > 10000 for s in sizes) and all(h == b"\x89PNG\r\n\x1a\n" for h in heads),
          f"{[s // 1024 for s in sizes]} kB, {dt:.1f} s")
    views = pg.load(os.path.join(outdir, "sol_1_views.json"))["views"]
    check("piece_views: the gameplay view follows sol_1's jump", "sol_1#0->sol_2#0" in views["gameplay"]["how"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", default=".")
    ap.add_argument("--blender", default=os.path.expanduser("~/opt/blender/blender"))
    ap.add_argument("--scratch")
    a = ap.parse_args()
    a.scratch = a.scratch or tempfile.mkdtemp(prefix="lfb_tools_")
    os.makedirs(a.scratch, exist_ok=True)
    a.fbx = os.path.join(a.project, FBX)
    a.kit_data = os.path.join(a.project, KIT_DATA)
    a.placement = os.path.join(a.project, PLACEMENT)
    a.guides = [os.path.join(a.project, g) for g in GUIDES]
    extract = os.path.join(a.scratch, "extract.json")
    t = time.time()
    test_inventory(a, os.path.join(a.scratch, "inventory.json"))
    test_extract(a, extract)
    test_shape_fit(a, extract)
    test_routes(a, extract)
    test_piece_views(a, extract)
    print(f"{len(FAILS)} failed, {time.time() - t:.1f} s, outputs in {a.scratch}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
