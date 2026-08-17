# Roboto Condensed source

- Distribution: Google Fonts `ofl/robotocondensed/RobotoCondensed[wght].ttf`
- Upstream metadata: `googlefonts/roboto-classic`, release v3.008, source commit
  `8aa699a9a715be7ecf6be41171e2851a580f0fb8`
- Downloaded: 2026-08-18
- TTF SHA-256: `dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0`
- License: SIL Open Font License 1.1; the exact text is retained in `OFL.txt`

`tools/generate_ui_gfx_font.py` selects the variable font's named `Medium`
instance (weight 500) before generating the 16 px body and 12 px metadata GFX
faces. The source TTF is never loaded at runtime.
