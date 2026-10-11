import os

import bpy

import art

GREY = "#808080"


def baked(a, stage):
    """`<slug>_mat`: one Principled material wired to a texture stage's maps, laid out as the glTF exporter expects
    (albedo → Base Color; ORM → occlusion R, roughness G, metallic B; tangent-space normal)."""
    name = f"{a.slug}_mat"
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    p = nt.nodes["Principled BSDF"]

    def tex(map_name, colorspace, x):
        path = a.texture(stage, map_name)
        if not os.path.exists(path):
            return None
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        n.image.colorspace_settings.name = colorspace
        n.location = (x, 0)
        return n

    albedo = tex("albedo", "sRGB", -700)
    if albedo:
        nt.links.new(albedo.outputs["Color"], p.inputs["Base Color"])
    orm = tex("orm", "Non-Color", -700)
    if orm:
        orm.location.y = -300
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        sep.location = (-400, -300)
        nt.links.new(orm.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], p.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], p.inputs["Metallic"])
        out = nt.nodes.new("ShaderNodeGroup")
        out.node_tree = gltf_output_group()
        out.location = (0, -500)
        nt.links.new(sep.outputs["Red"], out.inputs["Occlusion"])
    normal = tex("normal", "Non-Color", -700)
    if normal:
        normal.location.y = -650
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-400, -650)
        nt.links.new(normal.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    return mat


def gltf_output_group():
    ng = bpy.data.node_groups.get("glTF Material Output")
    if ng is None:
        ng = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        ng.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return ng


def preview(mat, swatch, normal=None, occlusion=None, darken=False):
    """mat, rebuilt as a flat stand-in for the engine's shared material of its zone: the swatch's colour,
    roughness and metallic, or neutral grey for a zone without a swatch. normal and occlusion are paths to the
    bake stage's maps, wired as glTF's normal and occlusion textures; it never carries a colour texture.

    darken: also multiply the colour by the occlusion, as an engine's ambient light does, for a render. glTF
    reads occlusion from its own slot, so an export leaves it off."""
    s = {**art.SWATCH, **(swatch or {"color": GREY})}
    rgba = (*art.linear(art.rgb(s["color"])), 1.0)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    nt.links.new(p.outputs["BSDF"], out.inputs["Surface"])
    p.inputs["Base Color"].default_value = rgba
    p.inputs["Roughness"].default_value = s["roughness"]
    p.inputs["Metallic"].default_value = s["metallic"]
    mat.diffuse_color, mat.roughness, mat.metallic = rgba, s["roughness"], s["metallic"]
    if normal:
        tex = _image(nt, normal, (-700, -650))
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-400, -650)
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    if occlusion:
        tex = _image(nt, occlusion, (-700, -300))
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        sep.location = (-400, -300)
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        group = nt.nodes.new("ShaderNodeGroup")
        group.node_tree = gltf_output_group()
        group.location = (0, -500)
        nt.links.new(sep.outputs["Red"], group.inputs["Occlusion"])
        if darken:
            mul = nt.nodes.new("ShaderNodeMix")
            mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            mul.inputs["A"].default_value = rgba
            nt.links.new(tex.outputs["Color"], mul.inputs["B"])
            nt.links.new(mul.outputs["Result"], p.inputs["Base Color"])
    return mat


def _image(nt, path, at):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path, check_existing=True)
    n.image.colorspace_settings.name = "Non-Color"
    n.location = at
    return n
