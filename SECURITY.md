# Security Policy

## Supported Versions

Eve Ratting is a single-script desktop tool. Only the **latest commit on
`main`** is supported with security fixes. Please make sure you are running
the most recent version before reporting an issue.

| Version | Supported          |
|---------|--------------------|
| `main` (latest) | :white_check_mark: |
| Older commits   | :x:                |

## Threat Model

Eve Ratting:

- Runs locally on the user's machine
- Reads files written by the EVE Online client (`Gamelogs`, `Chatlogs`)
- Writes its own JSON files (`ratting_config.json`, `ratting_history.json`,
  `ratting_prices.json`, `ratting_nameids.json`) next to the script
- May make outbound HTTPS requests to public EVE market/price endpoints to
  refresh the loot price cache
- Does **not** require, ask for, store, or transmit any EVE Online
  credentials, API keys, or session tokens
- Does **not** read or modify the EVE Online client process, memory, or
  network traffic

If you find behavior that contradicts any of the above, that is a security
issue and should be reported.

## What counts as a vulnerability

Examples of issues we treat as security-relevant:

- **Path traversal / arbitrary file read or write** through a crafted log
  line, config file, or history entry
- **Remote code execution** triggered by the contents of a log file,
  clipboard paste, downloaded price cache, or any other untrusted input
- **Insecure deserialization** of the JSON config / history / cache files
- **Outbound network calls** that send user-identifying data without
  consent
- **Crashes that corrupt user data** (e.g. `ratting_history.json` gets
  truncated or rewritten with garbage on a parser error)
- **Dependency vulnerabilities** in `pystray`, `Pillow` or `pyperclip` that
  Eve Ratting can be made to trigger

## What is NOT a vulnerability

- Crashes caused by manually editing `ratting_config.json` or
  `ratting_history.json` to invalid values
- The fact that history and config files are written in plain text — this
  is intentional, the data is not sensitive
- Themes that look ugly on a particular monitor
- Anything that requires the attacker to already have write access to the
  files in your project folder
- Concerns about the EVE Online EULA — see below

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Instead, report privately through one of these channels:

1. **GitHub Security Advisories** — preferred. Go to the repository's
   *Security* tab and click *Report a vulnerability*. This creates a
   private advisory only the maintainers can see.
2. **Direct contact** — message the repository owner
   [`@psychojf`](https://github.com/psychojf) on GitHub.

When reporting, please include:

- A clear description of the issue and its impact
- The version / commit hash you tested
- Step-by-step reproduction instructions
- A minimal proof of concept if you have one (a sample log line, a config
  snippet, etc.)
- Your suggested fix or mitigation, if any

## What to expect

- **Acknowledgement:** as soon as possible after we see the report
- **Triage:** we will confirm whether the issue reproduces and assess
  severity
- **Fix:** for confirmed issues, we will prepare a patch on a private
  branch
- **Disclosure:** once a fix is released, we will publish a short advisory
  crediting the reporter (unless you prefer to stay anonymous)

Because Eve Ratting is a small community project run on a best-effort
basis, we cannot offer a bug bounty, but credit in the release notes is
guaranteed for valid reports.

## EVE Online EULA / fair play

Eve Ratting is designed to stay strictly within CCP's Terms of Service: it
only reads files the EVE client writes to disk, with no automation, no
client modification, and no packet inspection. If you discover a way the
project crosses that line, please treat it as a security issue and report
it through the channels above.
