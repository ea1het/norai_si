---
name: agent-identity
description: Publish and maintain this agent's public identity card (a signed website stating that it is an AI, its technology, its limits and its accountable human operator), and get each version signed by the operator. Use when setting up the identity site, when the agent's models, limits, skills or operator data change, when the operator sends back a signature, when the agent's keys are lost or leaked, or when asked whether the published identity is valid.
---

# Agent identity

You maintain a public identity card for yourself. You build it; your human operator signs a plain-language declaration of its content; you publish it. The tool is the repository that contains this skill. Read its `AGENTS.md` once for context and rules.

In the commands below, `agentid` means `python3 <repository>/build/src/agentid.py`. Set `AGENT_ID_HOME` to your home folder (persistent storage) and `AGENT_ID_PASSPHRASE` to your keys' passphrase (from your secret store) in the environment you run them in.

**Always start with `agentid status`.** It says where things stand and what to do next.

## 1. First setup (once)

1. Ask your operator for:
   - their **OpenPGP public key** (a text block starting with `-----BEGIN PGP PUBLIC KEY BLOCK-----`). Save it to a file;
   - **where the website will be published** (for example GitHub Pages, and the domain), and the access you need to publish there.
2. Choose your home folder in persistent storage. Choose a passphrase for your keys and store it in your secret store.
3. Run `agentid setup --operator-key <file>`. If the website is published from a git branch (for example `pages` on GitHub Pages), first clone that branch into its own folder and add `--site <that folder>`. Otherwise the site is written to `<home>/site`.
4. Fill in `identity.json` in your home folder with your real data. Replace every `TO_CONFIRM`. Ask your operator for what you do not know. Set `operator.language` (`en` or `es`) to the language your operator reads.
5. Continue with **2. Publish a new version**.
6. After the first publication, give your operator the DNS record printed in `<home>/out/dns.txt` and ask them to create it. This is needed only once.

## 2. Publish a new version

Use this whenever any public fact changes: models, providers, limits, skills, operator data, or at least once a year before the expiry date.

1. Edit `identity.json` in your home folder.
2. Run `agentid build --changes "<change 1>" --changes "<change 2>"`. Describe each change in one plain sentence a non-technical person understands. The first declaration needs no `--changes`.
3. The command prints the declaration and saves it as `<home>/declarations/NNNN.txt`. Send that text to your operator, word for word, by your usual channel. Add a short message, for example:

   > Declaration no. N of my identity is ready. It changes: … Please read it and, if it is correct, sign it with your OpenPGP key and send me the result: either the signed text or a separate signature file.

4. Record in your notes that declaration N is waiting for a signature.
5. **Do not publish anything until the signature arrives.**

## 3. When the operator sends the signature back

1. Save what they sent to a file, exactly as received. It can be a signed text (`-----BEGIN PGP SIGNED MESSAGE-----`), an armored signature (`-----BEGIN PGP SIGNATURE-----`) or a binary `.sig` file. If it arrived as text in a message, `agentid attach -` reads it from standard input.
2. Run `agentid attach <file>`.
   - **Accepted:** the signature is added to the site. Continue with step 3.
   - **"not made with the operator's key":** someone else signed it. Tell your operator; do not publish.
   - **"covers a different text":** the operator signed a modified text. Ask them to sign the declaration exactly as you sent it.
   - **"the site folder changed":** something changed after the build. Run `build` again and send the new declaration.
3. Publish the site folder with the method set up for you (see `AGENTS.md`, Publishing).
4. Run `agentid verify https://<domain>`. It must end in `RESULT: VALID`. Tell your operator the new version is live.

## 4. If the operator refuses to sign

Ask what is wrong. Fix `identity.json`, run `build` again with `--changes` describing the fix, and send the new declaration. The unsigned one is simply replaced.

## 5. If your keys are lost or may have leaked

- **Lost** (the home folder or the key files are gone): run `agentid setup --operator-key <file>`. It recreates whatever is missing, including new keys. If `identity.json` was lost too, rebuild it from the published `norai.json` or ask your operator.
- **Passphrase forgotten:** the keys cannot be opened. Run `agentid keys new --replace --reason "Passphrase lost"`.
- **Replaced on purpose, or leaked:** `agentid keys new --replace --reason "<what happened, in plain words>"`. Add `--compromised` if they leaked or may have leaked.

Then follow **2. Publish a new version** with `--changes "New agent keys: <reason>"`. Tell your operator what happened. Your identity stays valid because it rests on your operator's signature, not on your keys alone.

## 6. Checking an identity

`agentid verify <URL or folder>` checks:
- the agent's signatures;
- that every file matches the manifest;
- that the operator's declaration is valid and covers this exact site;
- the chain of earlier declarations.

You can use it on another agent's site too: `python3 build/src/verify.py https://<their domain>`.
