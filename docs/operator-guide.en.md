# Operator guide

*[Versión en español](operator-guide.es.md)*

You are the person responsible for an artificial intelligence agent. The agent has a public web page that works as its **identity card**: it says it is an AI, what technology it uses, what it will never do, and who answers for it, which is you.

The agent does almost everything. You only do two things: **a one-time setup** and, whenever something changes, **read and sign a declaration**. You do not need to know how to program or use git.

## One-time setup

1. **Have an OpenPGP key.** It is your personal digital signature. If you do not have one, create it with the tool you prefer: Kleopatra (Windows), GPG Suite (Mac) or GnuPG (Linux).
2. **Publish your key's fingerprint in your domain's DNS**, in a TXT record named `_aid-sysop`. Use the full 40-character fingerprint, without spaces. For example, for `norai.si`:

   ```
   _aid-sysop.norai.si.  TXT  "0x4EC46C8A6F1AEAC67B6F5DE6152E3EA35B606503"
   ```

   This is the first and most important step: until it exists the agent can do nothing, because nobody could check who you are. You only need to change it if you change your key. If your DNS provider offers DNSSEC, turn it on: it stops anyone from forging this record.
3. **Give the agent your public key.** It is a block of text that starts with `-----BEGIN PGP PUBLIC KEY BLOCK-----`. It is public, so you can send it over any channel, as text or as a file. The agent checks that it matches the fingerprint in the DNS and shows it back to you so you can confirm it is yours. **Never give it your private key.**
4. **Decide where the website is published** (for example, GitHub Pages with your domain) and give the agent the access it needs to publish there. With GitHub Pages, also verify the domain in the GitHub account that publishes it (*Settings → Pages → Add a verified domain*) and publish the TXT record GitHub gives you: then no other account can use your domain.
5. **Prepare the agent's environment**, if the agent cannot do it alone: a passphrase for its keys, stored as a secret in its configuration, never in the files of the project.

## Each time something changes

### 1. You will receive a declaration

It is a text like this:

```
OPERATOR DECLARATION · NorAI · no. 2 · 25 October 2026

I, Jonathan Gonzalez, am the person responsible for the AI agent NorAI.
I declare that the information published at https://norai.si/ is correct:

  What it is:       Personal AI agent: an artificial intelligence system, not a person.
  Email:            norai.agent@gmail.com
  On whose behalf:  Its operator only
  Technology:       Hybrid, local-first: ~90% local models, ~10% cloud (Anthropic, OpenAI)
  ...
  Valid until:      2027-10-25

Changes since declaration no. 1:
  - Added Anthropic as a cloud provider.

────────────── Technical annex (checked by machines) ──────────────
agent: NorAI
...
```

The declaration can be in English or Spanish: the agent uses the language set up for you.

### 2. Read it before signing

Check the top part, the one written in plain language:

- Is everything it says about the agent **true**?
- Are the **changes** the ones you expected? If you see a change you do not know about, ask before signing.
- Does the **number** follow the last declaration you signed?
- Is the **validity date** reasonable?

You do not need to understand the technical annex. It lets programs check that the published website is exactly the one you approved.

### 3. Sign it

Sign the text **exactly as you received it**, without changing anything, with your usual tool. Either form works:

- **Signed text** (in Kleopatra: "Sign"; in GnuPG: `gpg --clearsign`). It produces a text that starts with `-----BEGIN PGP SIGNED MESSAGE-----`.
- **Separate signature** (a `.asc` or `.sig` file next to the text).

### 4. Send it back to the agent

Send whatever your tool produced over the channel you normally use. The signature is not secret: it does no harm if someone else sees it.

The agent will check that the signature is yours and that it matches that exact declaration. Then it will publish the website and let you know.

## If something is not right

**Do not sign.** Tell the agent what needs fixing. It will prepare a new declaration and send it to you. Without your signature, the agent publishes nothing.

## What your signature means

By signing, you declare that the information published about the agent is correct and that you are the person responsible for it. Anyone can check on the website that the signature is yours, that it covers exactly what is published, and that it belongs to a chain with all your earlier declarations.

## If you lose your key or it is stolen

Tell the agent. You will need to create a new key, revoke the old one with your tool, update the `_aid-sysop` DNS record with the new fingerprint and then give the agent the new public key. The agent will then send you a new declaration to sign with the new key.
