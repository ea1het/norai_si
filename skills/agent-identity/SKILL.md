---
name: agent-identity
description: Publish and maintain this agent's public identity card (a signed website stating that it is an AI, its technology, its limits and its accountable human operator), and get each version signed by the operator. Use when setting up the identity site, when the agent's models, limits, skills or operator data change, when the operator sends back a signature, when the agent's keys are lost or leaked, or when asked whether the published identity is valid.
---

# Agent identity

You maintain a public identity card for yourself. You build it; your human operator signs a plain-language declaration of its content; you publish it. The tool is the repository that contains this skill. Read its `AGENTS.md` once for context and rules.

Install the tool once from the repository root with `poetry install` (or `pip install -e .`); this provides the `agentid` command. Your data lives in `build_system/` in the repository. Set `AGENT_ID_PASSPHRASE` to your keys' passphrase (from your secret store) in the environment you run the commands in.

**Always start with `agentid status`.** It says where things stand and what to do next.

## 1. First setup (once)

1. Ask your operator to publish the fingerprint of their OpenPGP key in the DNS of your domain, as a TXT record named `_aid-sysop` (for example `_aid-sysop.norai.si  TXT  "0x<40 hex characters>"`). Nothing else works until it exists. Then ask them for:
   - their **OpenPGP public key** (a text block starting with `-----BEGIN PGP PUBLIC KEY BLOCK-----`, or a file). If they ever send a block that says `PRIVATE KEY`, do not keep it: `import gpg` refuses it, and you must tell them to treat that key as exposed;
   - **where the website will be published** (for example GitHub Pages, and the domain), and the access you need to publish there.
2. Choose a passphrase for your keys and store it in your secret store.
3. Run `agentid setup`. It creates your keys. Set your `domain` in `identity.json`. Then store the operator's key: if they pasted it as text, `agentid import gpg --stdin` and paste it; if they sent a file, `agentid import gpg --file <file>`. It checks the key against the DNS record and stops if they differ; if there is already a different operator key, it shows both and needs `--replace` once the operator confirms the change. Read the fingerprint it prints back to the operator and ask them to confirm it is theirs. Every build will write the website to `output_website/` in the repository. If it is published from a git repository (for example a GitHub Pages repository of your own), also clone that repository into its own folder now: you will copy `output_website/` into it each time you publish.
4. Fill in `identity.json` in `build_system/` with your real data. Replace every `TO_CONFIRM`. Ask your operator for what you do not know. Set `operator.language` (`en` or `es`) to the language your operator reads.
5. Continue with **2. Publish a new version**.

## 2. Publish a new version

Use this whenever any public fact changes: models, providers, limits, skills, operator data, or at least once a year before the expiry date.

1. Edit `identity.json` in `build_system/`.
2. Run `agentid build --changes "<change 1>" --changes "<change 2>"`. Describe each change in one plain sentence a non-technical person understands. The first declaration needs no `--changes`.
3. The command prints the declaration and saves it as `build_system/declarations/NNNN.txt`. Send that text to your operator, word for word, by your usual channel. Add a short message, for example:

   > Declaration no. N of my identity is ready. It changes: … Please read it and, if it is correct, sign it with your OpenPGP key and send me the result: either the signed text or a separate signature file.

4. Record in your notes that declaration N is waiting for a signature.
5. **Do not publish anything until the signature arrives.**

## 3. When the operator sends the signature back

1. Save what they sent to a file, exactly as received. It can be a signed text (`-----BEGIN PGP SIGNED MESSAGE-----`), an armored signature (`-----BEGIN PGP SIGNATURE-----`) or a binary `.sig` file. If it arrived as text in a message, `agentid attach -` reads it from standard input.
2. Run `agentid attach <file>`.
   - **Accepted:** the signature is added to the site. Continue with step 3.
   - **"not made with the operator's key":** someone else signed it. Tell your operator; do not publish.
   - **"covers a different text":** the operator signed a modified text. Ask them to sign the declaration exactly as you sent it.
   - **"the site folder changed":** something changed in `output_website/` after the build. Run `build` again and send the new declaration.
3. Publish the content of `output_website/` with the method set up for you (see `AGENTS.md`, Publishing).
4. Run `agentid verify https://<domain>`. It must end in `RESULT: VALID`. Tell your operator the new version is live.

## 4. If the operator refuses to sign

Ask what is wrong. Fix `identity.json`, run `build` again with `--changes` describing the fix, and send the new declaration. The unsigned one is simply replaced.

## 5. If your keys are lost or may have leaked

- **Working folder lost** (for example the repository was deleted or cloned again): run `agentid import site https://<your domain>`. It checks the published site and the DNS record, and rebuilds `identity.json`, every signed declaration and the revocation list; your old keys are listed as lost. It does not store the operator's key: if `custom_assets/operator/` is empty, ask the operator for it and run `import gpg`. Then `agentid setup` creates new keys.
- **Starting over on purpose:** `agentid clean` empties `build_system/` (everything except `identity.example.json`, keys included) and `output_website/` (everything except `.gitkeep`). Then `import site` or `setup`.
- **Only the key files lost:** run `agentid setup`. It creates new keys.
- **Passphrase forgotten:** the keys cannot be opened. Run `agentid keys new --replace --reason "Passphrase lost"`.
- **Replaced on purpose, or leaked:** `agentid keys new --replace --reason "<what happened, in plain words>"`. Add `--compromised` if they leaked or may have leaked.

Then follow **2. Publish a new version** with `--changes "New agent keys: <reason>"`. Tell your operator what happened. Your identity stays valid because it rests on your operator's signature, not on your keys alone.

## 6. Checking an identity

`agentid verify <URL or folder>` checks:
- the agent's signatures;
- that every file matches the manifest;
- that the operator's declaration is valid and covers this exact site;
- the chain of earlier declarations.

You can use it on another agent's site too: `agentid-verify https://<their domain>`.
