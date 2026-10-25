# NorAI · agent identity card

A public, verifiable identity card for an AI agent: a website that says it is an AI, what technology it uses, what it will never do, and which human answers for it. This supports the transparency duty of the EU AI Act (Article 50).

The agent does almost all the work: it keeps its data, builds the site and publishes it. Its human operator does the one thing that cannot be automated: **reading and signing a short declaration** with their OpenPGP key each time the public information changes. Anyone can then check that every published file is exactly what the operator approved.

This repository has two branches:

- **`main`**: the tool. Running it produces the agent's website.
- **`pages`**: the website it produced, which GitHub Pages serves at [norai.si](https://norai.si). The agent writes and publishes it; nobody edits it by hand.

## Where to start

| You are… | Read |
|---|---|
| An AI agent setting up or maintaining your identity | [AGENTS.md](AGENTS.md), then [skills/agent-identity/SKILL.md](skills/agent-identity/SKILL.md) |
| The human operator of an agent | [Operator guide](docs/operator-guide.en.md) · [Guía del operador](docs/operator-guide.es.md) |
| Curious about keys, signatures and verification | [How it works](docs/how-it-works.en.md) · [Cómo funciona](docs/how-it-works.es.md) |
| Checking someone's agent identity | `python3 build/src/verify.py https://<their domain>` |

## Try it

```bash
poetry install          # or: pip install cryptography segno   (GnuPG is needed too)
python3 build/src/agentid.py demo
```

This builds a complete demo site in `build/demo/site/`, with throwaway keys and a demo operator, and verifies it. Do not publish a demo build.

## Licence

Mozilla Public License 2.0. See [LICENSE](LICENSE).
