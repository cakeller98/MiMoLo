# MiMoLo Utils (TypeScript)

Shared TS utilities and experiments. This project targets Node.js 24.11.1.

## Setup

```bash
cd mimolo/utils
npm install
```

## Build/Run

```bash
npm run build
npm run start
```

## Release Pack Agent

Builds a versioned zip from a field-agent folder that contains a build manifest.

```bash
npm run build
node dist/release-pack-agent.js --source <agent_dir> [--out <out_dir>]
```

Or run directly with tsx:

```bash
npm install
npm run release-pack-agent:tsx -- --source <agent_dir> [--out <out_dir>]
```

### Version bump flags

Release flags (mutually exclusive):
- `--major`
- `--minor`
- `--patch`

Prerelease flags (mutually exclusive):
- `--alpha`
- `--beta`
- `--rc`

You may combine one release flag with one prerelease flag.

Alpha/beta follow semver prerelease rules. Example:
- `0.4.0-alpha.2` + `--alpha` -> `0.4.0-alpha.3`
- `0.4.0-alpha.3` + `--beta` -> `0.4.0-beta.0`
- `0.4.0-beta.0` + `--alpha` -> `0.4.0-alpha.0`

RC example:
- `1.2.3-beta.2` + `--rc` -> `1.2.3-rc.0`

Combined example:
- `2.5.0` + `--major --rc` -> `3.0.0-rc.0`

Note:
- Combined release + prerelease uses semver premajor/preminor/prepatch rules, so
  `1.0.1-beta.0` + `--major --beta` -> `2.0.0-beta.0`.

### build-manifest.toml (required)

```toml
plugin_id = "agent_template"
name = "Agent Template"
version = "0.1.0"
entry = "files/agent_template.py"
files = ["agent_template.py"]
```

Output zip layout:

```
<plugin_id>/
  manifest.json
  payload_hashes.json
  files/
    <files listed in build-manifest.toml>
```

Notes:
- If `--out` is a relative path, it is resolved relative to `--source`.
- If `--out` is omitted, the default is `<source>/../repository`.
