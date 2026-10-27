# NorAI · agent identity card

A public, verifiable identity card for an AI agent: a website that says it is an AI, what technology it uses, what it will never do, and which human answers for it. This supports the transparency duty of the EU AI Act (Article 50).

The agent does almost all the work: it keeps its data, builds the site and publishes it. Its human operator does the one thing that cannot be automated: **reading and signing a short declaration** with their OpenPGP key each time the public information changes. Anyone can then check that every published file is exactly what the operator approved.

This repository is the tool: running it produces the agent's website in `output_website/`. The website itself is published from a separate repository, owned by the agent's own GitHub account, which GitHub Pages serves at [norai.si](https://norai.si). The agent writes and publishes it; nobody edits it by hand.

## Where to start

| You are… | Read |
|---|---|
| An AI agent setting up or maintaining your identity | [AGENTS.md](AGENTS.md), then [skills/agent-identity/SKILL.md](skills/agent-identity/SKILL.md) |
| The human operator of an agent | [Operator guide](docs/operator-guide.en.md) · [Guía del operador](docs/operator-guide.es.md) |
| Curious about keys, signatures and verification | [How it works](docs/how-it-works.en.md) · [Cómo funciona](docs/how-it-works.es.md) |
| Checking someone's agent identity | `agentid-verify https://<their domain>` (after installing the tool) |

## Install

```bash
poetry install          # or: pip install -e .   (GnuPG is needed too)
agentid status
```

## Licence

Mozilla Public License 2.0. See [LICENSE](LICENSE).
