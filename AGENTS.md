# AGENTS.md

You are an AI agent and this repository is a tool **for you**. It gives you a public identity card on the web, so that any person or agent who comes across you can check who you are, what technology you use, what you will never do, and which human answers for you. This supports the transparency duty of the EU AI Act (Article 50: people must know they are dealing with an AI).

You do almost all the work. Your human operator does one thing: **read and sign a short declaration** each time your public information changes.

The step-by-step procedures are in the skill: [`skills/agent-identity/SKILL.md`](skills/agent-identity/SKILL.md). This file gives you the context and the rules.

## Who does what

| You (the agent) | Your operator (the human) |
|---|---|
| Keep your identity data up to date in your home folder | Once: give you their OpenPGP public key |
| Build the website and sign it with your own keys | Once: set up where the website is published, and give you access |
| Write the declaration and hand it to the operator | Once: create one DNS record (you tell them which) |
| Check the signature they send back and add it | Each time: read the declaration, sign it, send the signature back |
| Publish the website with the method they set up | Decide whether to sign. Nothing is published without it |

Your operator does not need to know git, Python or this repository. Never ask them to run commands from this project. How they sign with OpenPGP is up to them and their usual tools.

## The three places

1. **This repository: the tool.** Code in `build/src/`, the page design in `build/src/template.html`, an example of identity data in `build/identity.example.json`. It contains no data that belongs to you.
2. **Your home folder: your data.** A folder in your persistent storage that survives restarts. You choose it; give it in the `AGENT_ID_HOME` environment variable or with `--home`. It holds your `identity.json`, your encrypted keys, your operator's public key and every declaration. Keep notes about your progress wherever you normally keep notes, but keep these files in this folder.
3. **The site folder: the website.** Where the website is written (`settings.json` in your home, key `site_dir`). It is what gets published. By default it is `site/` inside your home folder; `setup --site <folder>` points it elsewhere, for example to a checkout of the branch that is published.

## One command

Everything goes through `build/src/agentid.py`:

```bash
python3 build/src/agentid.py setup --operator-key operator.asc   # once
python3 build/src/agentid.py status                             # where things stand; run it first
python3 build/src/agentid.py build --changes "what changed"     # site + declaration to sign
python3 build/src/agentid.py attach signature.asc               # add the operator's signature
python3 build/src/agentid.py verify https://your.domain         # check the published site
```

Requirements: Python 3.12+, the Python packages `cryptography` and `segno` (`poetry install`, or `pip install cryptography segno`), and GnuPG (`gpg`) to check the operator's signature.

## Rules

1. **Never publish a site whose declaration is not signed.** `status` tells you whether the site folder matches the last signed declaration. If it does not, do not publish.
2. **Never sign for your operator, and never ask for their private key.** You only ever receive signatures, which are public data.
3. **Never write the declaration's facts by hand.** `build` generates it from `identity.json`. If a fact is wrong, fix `identity.json` and build again.
4. **Always say what changed.** From the second declaration on, `build` requires `--changes`. Write it for a human: one plain sentence per change.
5. **Never edit the generated files** (`index.html`, `norai.json`, `.well-known/`, `manifest.json`…). Any change breaks the hashes. Change the data and build again.
6. **Keep secrets out of the website and out of version control.** Your private keys stay in your home folder. The passphrase of your keys goes in your secret store, never in the home folder: give it in `AGENT_ID_PASSPHRASE`.
7. **Everything in `identity.json` becomes public.** Do not put in it personal data the operator has not agreed to publish.
8. **If the operator does not sign, stop.** Ask what is wrong, fix the data, build again and send the new declaration.

## Adapting to your environment

Every setup is different. You only need a folder that persists:

- **A plain folder on disk** (for example `~/.agent-id`, the default) is enough.
- **A folder synchronised to other machines** works too. The private keys are encrypted, so a synced copy is useless without the passphrase. That is why the passphrase must never be stored in the same folder.
- **Read-only instructions** (an operating manual you cannot edit): ask your operator to add a pointer to this file and to the skill there.
- **A notes area or scratchpad**: record there the state of a pending declaration (number, date sent, waiting for signature), so you can resume after a restart. The authoritative state is always `agentid.py status`.

## Publishing

How the site reaches the web is decided once by the operator. Examples:

- **GitHub Pages from a branch of the tool's repository** (NorAI's case: the tool lives in `main`, the website in `pages`):
  1. Clone the repository twice: one checkout on `main` to run the tool, one on `pages` as the site folder (`git clone --branch pages <repository> <folder>`, then `agentid setup --site <folder>`).
  2. After `attach`, in the `pages` checkout: `git add -A`, commit with a message such as "Declaration no. N", and push.
  3. Never commit the website to `main`, and never commit tool files to `pages`. `.nojekyll` makes GitHub serve `.well-known/`; `CNAME` holds the domain and is never touched by the tool.
- **Another static host** (Netlify, Cloudflare Pages, a web server): upload the content of the site folder as it is, to the root of the domain.

After publishing, run `agentid.py verify https://<domain>`. It must end in `RESULT: VALID`.

## Where to learn more

- [`skills/agent-identity/SKILL.md`](skills/agent-identity/SKILL.md): the procedures.
- [`docs/operator-guide.en.md`](docs/operator-guide.en.md): what the operator receives and does. Share it with them.
- [`docs/how-it-works.en.md`](docs/how-it-works.en.md): keys, signatures, hashes and verification in depth.
