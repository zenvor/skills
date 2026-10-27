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
| [macos-v2rayn-troubleshooting](skills/macos-v2rayn-troubleshooting/) | Diagnoses macOS v2rayN TUN errors, stale Fake-IP mappings, background services, and IMAP TLS connections |
| [minecraft-bedrock-server-deployment](skills/minecraft-bedrock-server-deployment/) | Safely assesses, deploys, migrates, and verifies Minecraft Bedrock servers |
| [syncthing-direct-file-transfer](skills/syncthing-direct-file-transfer/) | Transfers files directly with Syncthing on macOS and Windows, disables relays, and verifies source hashes; Windows native validation is pending |
| [vless-xhttp-tls-cloudflare-cdn](skills/vless-xhttp-tls-cloudflare-cdn/) | Deploys and verifies VLESS + XHTTP + TLS nodes through Cloudflare CDN, including origin certificates, strict TLS, dedicated clients, and subscription exports |
| [x-media-download](skills/x-media-download/) | Reliably archives every image and video from an X profile and organizes media by post |

## Compatibility

Skills follow the open [Agent Skills specification](https://agentskills.io/specification) and use portable `SKILL.md`, `scripts/`, and `references/` conventions. Client-specific metadata, such as `agents/openai.yaml`, is optional and can be ignored by clients that do not use it.

## License

MIT
