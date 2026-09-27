# Material values

The starting points for zone materials, in metallic–roughness PBR as glTF stores it. Albedo is sRGB, as picked by eye; pass it through `nodes.srgb`.

| material | albedo (sRGB) | roughness | metallic |
|---|---|---|---|
| charcoal, soot | #323232 – #3c3c3c | 0.8–0.95 | 0 |
| dark wood | #3e2a1c – #5a3a24 | 0.6–0.85 | 0 |
| light wood | #8a6a4a – #c4a27a | 0.55–0.8 | 0 |
| stone, concrete | #6a6a64 – #b4b2aa | 0.7–0.95 | 0 |
| skin | #8d5a45 – #e8c2a8 | 0.45–0.65 | 0 |
| fabric | any hue, value 40–220 | 0.75–1.0 | 0 |
| leather | #3a2418 – #8a5a3a | 0.4–0.7 | 0 |
| plastic, paint | any hue, value 40–230 | 0.2–0.6 | 0 |
| iron, steel | #a8aaae – #c4c7c7 | 0.3–0.6 | 1 |
| rusted iron | #5a3a2a – #8a5a3a | 0.7–0.9 | 0 (rust is not metal) |
| gold | #f0cc80 – #ffe29d | 0.2–0.4 | 1 |
| copper | #e8b8a0 – #fad1c2 | 0.25–0.45 | 1 |
| snow | #dcdfe4 – #f2f3f5 | 0.6–0.8 | 0 |

- **Metallic is 0 or 1.** Only the transition pixels between metal and non-metal (a worn edge, a rust patch's border) take values in between. Dirt, rust or paint lying on a metal is non-metal.
- **PBR albedo** stays within 30–243 sRGB. It carries no shadows, highlights or AO; the engine and the ORM map add those.
- **Stylized albedo** carries the lighting, so it may leave that range. Its ORM occlusion is white, so the engine doesn't darken it a second time.
- **Specular.** Core glTF has no specular map. Roughness sets the size and sharpness of the highlight, and non-metals reflect a fixed 4%. A reference that shows "specular" detail (wet streaks, polished wear) is a roughness pattern.
