"""Art guide invariants (pipeline/ART.md), run inside Blender:
    ~/opt/blender/blender --background --factory-startup --python pipeline/tests/test_art.py
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

ROOT = tempfile.mkdtemp(prefix="art_test_")
os.environ["ASSETS_DIR"] = ROOT
HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, "..", "templates", "art")
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import bpy  # noqa: E402

import art  # noqa: E402
import asset as asset_mod  # noqa: E402
import imgio  # noqa: E402

ART = asset_mod.ART
LIMITS = asset_mod.LIMIT_DEFAULTS
WORLD = "azeroth"
ZONE = "azeroth/duskwood"
CHAIN = "azeroth/duskwood/human_village"
PLACES = {"world_art.md": WORLD, "zone_art.md": ZONE, "set_art.md": CHAIN}


def install_examples():
    shutil.rmtree(ART, ignore_errors=True)
    for name, where in PLACES.items():
        os.makedirs(os.path.join(ART, where), exist_ok=True)
        shutil.copy(os.path.join(EXAMPLES, f"{name}.example"), os.path.join(ART, where, name))


def write_guide(where, name, *blocks):
    body = "\n".join(f"```json\n{json.dumps(b)}\n```\n" for b in blocks)
    with open(os.path.join(ART, where, name), "w") as f:
        f.write(f"# test guide\n\n{body}")


def rules(chain=CHAIN):
    return art.merge(art.chain(ART, chain), LIMITS)


def rejects(fn, words):
    try:
        fn()
    except SystemExit as e:
        assert words in str(e.code), f"expected '{words}' in: {e.code}"
        return
    raise AssertionError(f"expected a rejection mentioning '{words}'")


def new_asset(slug, **spec):
    d = os.path.join(ROOT, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "asset.json"), "w") as f:
        json.dump({"slug": slug, **spec}, f)
    return asset_mod.Asset(slug)


def test_examples_merge_world_then_zone_then_set():
    r = rules()
    assert r["texture_mode"] == "stylized"
    assert r["limits"]["albedo_luma"] == [28, 160], "the zone's value key replaces the world's"
    assert r["limits"]["min_zone_contrast"] == 24, "a world limit holds where the zone is silent"
    assert r["painted_light"]["key"] == [-0.45, -0.55, 0.7], "the world owns the key direction"
    assert r["painted_light"]["wrap"] == 0.2, "the zone's light overrides the world's key by key"
    assert {"timber", "iron", "glow"} <= set(r["palette"]), "zone and set palettes merge"
    assert r["kit"]["bay"] == 2.0


def test_a_lower_guide_cannot_loosen_a_max():
    write_guide(ZONE, "zone_art.md", {"limits": {"max_saturation": 0.9}})
    rejects(lambda: rules(ZONE), "loosens")


def test_a_lower_guide_cannot_widen_a_range():
    write_guide(ZONE, "zone_art.md", {"limits": {"albedo_luma": [10, 160]}})
    rejects(lambda: rules(ZONE), "loosens")


def test_a_lower_guide_cannot_lower_a_min():
    write_guide(ZONE, "zone_art.md", {"limits": {"min_zone_contrast": 12}})
    rejects(lambda: rules(ZONE), "loosens")


def test_a_lower_guide_cannot_switch_a_limit_off():
    write_guide(ZONE, "zone_art.md", {"limits": {"max_saturation": None}})
    rejects(lambda: rules(ZONE), "loosens")


def test_a_lower_guide_may_tighten():
    write_guide(ZONE, "zone_art.md", {"limits": {"albedo_luma": [30, 120], "min_zone_contrast": 30}})
    assert rules(ZONE)["limits"]["albedo_luma"] == [30, 120]


def test_unknown_rules_and_limits_are_rejected():
    write_guide(ZONE, "zone_art.md", {"colours": {}})
    rejects(lambda: rules(ZONE), "unknown rules")
    write_guide(ZONE, "zone_art.md", {"limits": {"max_saturaton": 0.5}})
    rejects(lambda: rules(ZONE), "not limits")


def test_helper_blocks_take_only_the_helpers_keywords():
    write_guide(ZONE, "zone_art.md", {"painted_light": {"strength": 1}})
    rejects(lambda: rules(ZONE), "painted_light takes")
    write_guide(ZONE, "zone_art.md", {"painted_light": {"top": [0, 1]}})
    rejects(lambda: rules(ZONE), "painted_light takes")


def test_a_key_set_twice_in_one_guide_is_rejected():
    write_guide(ZONE, "zone_art.md", {"limits": {"max_saturation": 0.5}}, {"limits": {"max_saturation": 0.4}})
    rejects(lambda: rules(ZONE), "set in two blocks")


def test_blocks_of_one_guide_join():
    write_guide(ZONE, "zone_art.md", {"limits": {"max_saturation": 0.5}}, {"limits": {"albedo_luma": [20, 200]}})
    assert rules(ZONE)["limits"] == {**rules(WORLD)["limits"], "max_saturation": 0.5, "albedo_luma": [20, 200]}


def test_every_plain_swatch_sits_inside_the_value_key():
    write_guide(ZONE, "zone_art.md", {"limits": {"albedo_luma": [28, 160]},
                                      "palette": {"bone": {"color": "#e8e4dc"}}})
    rejects(lambda: rules(ZONE), "outside limits.albedo_luma")
    write_guide(ZONE, "zone_art.md", {"limits": {"max_saturation": 0.45},
                                      "palette": {"blood": {"color": "#a01010"}}})
    rejects(lambda: rules(ZONE), "above limits.max_saturation")


def test_accents_may_leave_the_value_key():
    write_guide(ZONE, "zone_art.md", {"limits": {"albedo_luma": [28, 160]},
                                      "palette": {"bone": {"color": "#e8e4dc", "accent": True}}})
    assert rules(ZONE)["palette"]["bone"]["accent"] is True


def test_touching_swatches_keep_the_contrast_floor():
    write_guide(ZONE, "zone_art.md", {"palette": {"trunk": {"color": "#505050", "touches": ["soil"]},
                                                  "soil": {"color": "#585858"}}})
    rejects(lambda: rules(ZONE), "touch but sit 8 luma apart")
    write_guide(ZONE, "zone_art.md", {"palette": {"trunk": {"color": "#505050", "touches": ["ghost"]}}})
    rejects(lambda: rules(ZONE), "which no guide on the chain names")
    write_guide(ZONE, "zone_art.md", {"palette": {"trunk": {"color": "#505050", "touches": "soil"}}})
    rejects(lambda: rules(ZONE), "list of swatch names")


def test_every_palette_problem_is_reported_in_one_run():
    write_guide(ZONE, "zone_art.md", {"limits": {"max_saturation": 0.45},
                                      "palette": {"trunk": {"color": "#505050", "touches": ["soil", "moss"]},
                                                  "soil": {"color": "#585858"}, "moss": {"color": "#545454"},
                                                  "blood": {"color": "#a01010"}}})
    try:
        rules(ZONE)
    except SystemExit as e:
        msg = str(e.code)
        assert "soil and trunk" in msg and "moss and trunk" in msg and "palette.blood" in msg, msg
        return
    raise AssertionError("expected a rejection")


def test_the_examples_declare_their_touching_pairs():
    pairs = {(a, b) for a, b, _ in art.touching(rules())}
    assert ("planks", "timber") in pairs and ("earth", "stone") in pairs, "set swatches pair with zone swatches"


def test_a_chain_needs_every_guide_it_names():
    rejects(lambda: art.chain(ART, "nowhere"), "needs")
    rejects(lambda: art.chain(ART, "a/b/c/d"), "levels")


def test_an_asset_follows_only_the_chain_it_names():
    assert art.chain(ART, None) == [], "no art field, no guides, however many worlds exist"
    assert new_asset("unguided_probe").art == {}
    assert art.chains(ART) == [WORLD, ZONE, CHAIN]


def test_the_sheet_draws_every_swatch_darkest_first():
    path = os.path.join(ROOT, "sheet.png")
    r = rules()
    art.sheet(r, path, cell=8)
    px = imgio.read(path)
    assert px.shape[:2] == (8 * len(r["palette"]), 32)
    top, bottom = px[-1, 12, :3], px[0, 12, :3]
    assert float(art.luma(top)) < float(art.luma(bottom)), "row 0 is at the bottom; the darkest swatch is on top"


def test_asset_limits_override_the_guides_and_texture_mode_defaults_from_them():
    a = new_asset("limits_probe", art=CHAIN, texture_mode=None, limits={"max_saturation": 0.6})
    assert a.limits["max_saturation"] == 0.6, "asset.json is the last word for one asset"
    assert a.limits["albedo_luma"] == [28, 160]
    assert a.spec["texture_mode"] == "stylized"


def test_fingerprint_follows_the_rules():
    before = new_asset("fingerprint_probe", art=CHAIN).fingerprint()
    path = os.path.join(ART, CHAIN, "set_art.md")
    with open(path) as f:
        text = f.read()
    with open(path, "w") as f:
        f.write(text.replace("#9a9286", "#948c80"))
    assert new_asset("fingerprint_probe", art=CHAIN).fingerprint() != before


def test_zone_table_takes_swatches_and_fills_the_rest_locally():
    a = new_asset("table_probe", art=CHAIN)
    me = bpy.data.meshes.new("table_probe")
    obj = bpy.data.objects.new("table_probe", me)
    bpy.context.scene.collection.objects.link(obj)
    for zone in ("timber", "main"):
        me.materials.append(bpy.data.materials.new(f"zone_{zone}"))
    table = a.zone_table({"main": ("#808080", 0.9, 0)})
    assert table == {"timber": ("#3f3129", 0.85, 0), "main": ("#808080", 0.9, 0)}
    rejects(lambda: a.zone_table({"main": ("#808080", 0.9, 0), "timber": ("#000000", 0.5, 0)}), "change it there")
    rejects(lambda: a.zone_table({}), "needs a colour")
    rejects(lambda: a.zone_table({"main": ("#808080", 0.9, 0), "trim": ("#606060", 0.9, 0)}), "no zone for")
    bpy.data.objects.remove(obj)


def main():
    failed = 0
    for name, fn in [(n, f) for n, f in globals().items() if n.startswith("test_")]:
        install_examples()
        try:
            fn()
            print(f"PASS {name}")
        except (Exception, SystemExit):
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    shutil.rmtree(ROOT, ignore_errors=True)
    print(f"{failed} failed" if failed else "all passed")
    sys.exit(1 if failed else 0)


main()
