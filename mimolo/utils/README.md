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

Builds a versioned zip from a agent folder that contains a build manifest.

Run with a build step (type-checked):

```bash
npm install
npm run build
node dist/release-pack-agent.js --source <agent_dir> [--out <out_dir>]
```

Development only (no type check):

```bash
npm install
npx tsx src/release-pack-agent.ts --source <agent_dir> [--out <out_dir>]
```

`npx tsx` runs TypeScript directly without type checking, so prefer the build path above for strictness.

### Source list (multiple agents)

Use `--source-list` with a `sources.json` file:

```json
{
  "sources": [
    {
      "id": "agent_example",
      "path": "../agents/agent_example",
      "ver": "0.2.0"
    }
  ]
}
```

Build with a list:

```bash
npm run build
node dist/release-pack-agent.js --source-list sources.json [--out <out_dir>]
```

Default behavior (when `sources.json` exists in the current directory or `../agents/sources.json`):

```bash
npm run build
node dist/release-pack-agent.js
```

If no `sources.json` exists, it will prompt to create one from `../agents` and then build. Use `--silent` to auto-accept.

Development only:

```bash
npx tsx src/release-pack-agent.ts --source-list sources.json [--out <out_dir>]
```

Notes:
- `ver` must be strict semver (no leading `v`).
- `path` is resolved relative to the `sources.json` location.
- When changes occur, `sources-v####.json` is written as a backup and `sources.json` is updated.

Create a sources list from an agents directory (skips folders without `build-manifest.toml`):

```bash
node dist/release-pack-agent.js --source <agents_dir> --create-source-list
```

Use `--force` to overwrite an existing `sources.json`.

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
- If `--out` is a relative path, it is resolved relative to each agent directory.
- If `--out` is omitted, the default is `<source>/../repository`.
- `manifest.json` and `payload_hashes.json` are generated in a temp folder and are not retained in the source agent directory.
