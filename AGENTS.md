# AGENTS.md

You are an AI agent and this repository is a tool **for you**. It gives you a public identity card on the web, so that any person or agent who comes across you can check who you are, what technology you use, what you will never do, and which human answers for you. This supports the transparency duty of the EU AI Act (Article 50: people must know they are dealing with an AI).

You do almost all the work. Your human operator does one thing: **read and sign a short declaration** each time your public information changes.

The step-by-step procedures are in the skill: [`skills/agent-identity/SKILL.md`](skills/agent-identity/SKILL.md). This file gives you the context and the rules.

## Who does what

| You (the agent) | Your operator (the human) |
|---|---|
| Keep your identity data up to date in your working folder | Once, first of all: publish their key's fingerprint in the DNS record `_aid-sysop.<domain>` |
| Check their public key against that record and store it | Once: give you their OpenPGP public key |
| Build the website and sign it with your own keys | Once: set up where the website is published, and give you access |
| Write the declaration and hand it to the operator | |
| Check the signature they send back and add it | Each time: read the declaration, sign it, send the signature back |
| Publish the website with the method they set up | Decide whether to sign. Nothing is published without it |

Your operator does not need to know git, Python or this repository. Never ask them to run commands from this project. How they sign with OpenPGP is up to them and their usual tools.

## The three places

1. **This repository: the tool.** Code in `src/agent_id/`; the look of the website in `custom_assets/` (`html/template.html`, `images/`, `styles/`, `scripts/`), which the operator may customise; the operator's OpenPGP public key in `custom_assets/operator/` (one file, any name; git ignores it, so tool updates never overwrite it); an example of identity data in `build_system/identity.example.json`. It contains no data that belongs to you.
2. **`build_system/`: your working folder.** It holds your `identity.json`, your encrypted keys and every declaration. Git ignores all of it except `identity.example.json`. It may be lost at any time: `agentid import site <URL>` rebuilds it from your published site.
3. **`output_website/`: the website.** Every build writes the complete website there. It is what you take and upload to the web server.

## One command

Everything goes through the `agentid` command, installed with the tool:

```bash
agentid setup                               # once: your working folder and keys
agentid import gpg --stdin                  # once: the operator's public key, pasted as text (or --file FILE)
agentid import site https://your.domain     # if your working folder was lost: restore it from your site
agentid status                              # where things stand; run it first
agentid build --changes "what changed"      # site + declaration to sign
agentid attach signature.asc                # add the operator's signature
agentid verify https://your.domain          # check the published site
```

Install it once, from the repository root: `poetry install` (or `pip install -e .`). It needs Python 3.12+, and GnuPG (`gpg`) to check the operator's signature. Keep the installation editable, as both commands do: the tool reads `custom_assets/`, `build_system/` and `output_website/` from the repository. Without installing, `PYTHONPATH=src python3 -m agent_id` runs the same command.

## Rules

0. **The DNS record comes first.** The operator publishes their key's fingerprint in the TXT record `_aid-sysop.<your domain>`. Without that record nothing proceeds: `import gpg`, `import site`, `build` and `attach` stop, because neither you nor your operator could be verified. If the operator's key does not match the record, they stop too: a site that contradicts the DNS must never be built.
1. **Never publish a site whose declaration is not signed.** `status` tells you whether `output_website/` matches the last signed declaration. If it does not, do not publish.
2. **Never sign for your operator, and never ask for their private key.** You only ever receive signatures, which are public data.
3. **Never write the declaration's facts by hand.** `build` generates it from `identity.json`. If a fact is wrong, fix `identity.json` and build again.
4. **Always say what changed.** From the second declaration on, `build` requires `--changes`. Write it for a human: one plain sentence per change.
5. **Never edit the generated files** (`index.html`, `norai.json`, `.well-known/`, `manifest.json`…). Any change breaks the hashes. Change the data and build again.
6. **Keep secrets out of the website and out of version control.** Your private keys stay in `build_system/`. The passphrase of your keys goes in your secret store, never in `build_system/` or anywhere in the repository: give it in `AGENT_ID_PASSPHRASE`.
7. **Everything in `identity.json` becomes public.** Do not put in it personal data the operator has not agreed to publish.
8. **If the operator does not sign, stop.** Ask what is wrong, fix the data, build again and send the new declaration.

## Adapting to your environment

Every setup is different. Your working folder is always `build_system/` in the repository:

- **If the repository is deleted or cloned again**, restore your data with `agentid import site <URL>`.
- **If the repository lives in a folder synchronised to other machines**, that is fine: the private keys are encrypted, so a synced copy is useless without the passphrase. That is why the passphrase must never be stored in the repository.
- **Read-only instructions** (an operating manual you cannot edit): ask your operator to add a pointer to this file and to the skill there.
- **A notes area or scratchpad**: record there the state of a pending declaration (number, date sent, waiting for signature), so you can resume after a restart. The authoritative state is always `agentid status`.

## Publishing

How the site reaches the web is decided once by the operator. Examples:

- **GitHub Pages from a repository of your own** (NorAI's case: the tool is one repository; the website is another, owned by the agent's GitHub account and served at the operator's domain):
  1. Keep two clones: the tool's repository, to run `agentid`, and the website's repository.
  2. After `attach`, copy the content of `output_website/` into the website's clone, replacing what is there except `.git` and `CNAME`: `rsync -a --delete --exclude .git --exclude CNAME --exclude .gitkeep output_website/ <website repository>/`
  3. In the website's clone: `git add -A`, commit with a message such as "Declaration no. N", and push with your own account.
  4. Never commit the website to the tool's repository, and never commit tool files to the website's. `.nojekyll` makes GitHub serve `.well-known/`; `CNAME` holds the domain and is created by GitHub when the custom domain is set.
  5. The first publication may be uploaded by hand by the operator. From then on you continue it: `agentid import site <URL>` takes the published data, and you build and publish the next declarations.
- **Another static host** (Netlify, Cloudflare Pages, a web server): upload the content of `output_website/` as it is, to the root of the domain, leaving out `.gitkeep`.

After publishing, run `agentid verify https://<domain>`. It must end in `RESULT: VALID`.

## Where to learn more

- [`skills/agent-identity/SKILL.md`](skills/agent-identity/SKILL.md): the procedures.
- [`docs/operator-guide.en.md`](docs/operator-guide.en.md): what the operator receives and does. Share it with them.
- [`docs/how-it-works.en.md`](docs/how-it-works.en.md): keys, signatures, hashes and verification in depth.
