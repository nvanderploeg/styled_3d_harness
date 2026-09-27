import os

import bpy


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
