# drawio-skill vendor resources

Runtime resources vendored from the drawio-skill upstream repository for the HLD Design generation service.

## Upstream

- **Repository**: https://github.com/Agents365-ai/drawio-skill
- **Commit SHA**: 795776fed19023ac646023af2feec4f7ee0e4d72
- **Synced date**: 2026-05-20

## Vendored files

| File | Purpose |
|------|---------|
| `SKILL.md` | XML structure reference, shape styles, connector rules, export commands |
| `references/diagram-types.md` | Architecture diagram preset (shape vocabulary, layout conventions) |
| `references/troubleshooting.md` | Error recovery for export failures, CLI issues, rendering problems |
| `scripts/repair_png.py` | Fixes truncated IEND chunk in draw.io `-e` PNG exports |
| `styles/built-in/corporate.json` | Corporate style preset (sharp rectangles, Material Design colors) |
| `styles/built-in/default.json` | Default style preset (rounded shapes, standard palette) |
| `styles/schema.json` | JSON Schema for style preset validation |

## How to update

1. `cd /tmp && git clone https://github.com/Agents365-ai/drawio-skill.git drawio-skill-update`
2. Re-copy the files listed above from `drawio-skill-update/skills/drawio-skill/`
3. Update the Commit SHA and Synced date in this README
4. Run `cd quote-agent && python -m pytest tests/ -v` to verify no regressions
