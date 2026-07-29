# skills

A collection of [Agent Skills](https://agentskills.io) — shareable, on-demand knowledge for AI agents.

## Installation

Install a specific skill:

```bash
npx skills add https://github.com/zenvor/skills --skill <skill-name>
```

Install all skills:

```bash
npx skills add https://github.com/zenvor/skills
```

## Skills

| Name | Description |
|------|-------------|
| [create-openpeon-sound-pack](skills/create-openpeon-sound-pack/) | Creates and publishes CESP v1.0 compatible sound packs for peon-ping |
| [deploy-minecraft-bedrock-server](skills/deploy-minecraft-bedrock-server/) | Safely assesses, deploys, migrates, and verifies Minecraft Bedrock servers |

## Compatibility

Skills follow the open [Agent Skills specification](https://agentskills.io/specification) and use portable `SKILL.md`, `scripts/`, and `references/` conventions. Client-specific metadata, such as `agents/openai.yaml`, is optional and can be ignored by clients that do not use it.

## License

MIT
