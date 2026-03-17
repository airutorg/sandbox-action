# Airut Sandbox Action

GitHub Action that runs CI commands inside a sandboxed container with network
restrictions and credential isolation. Designed for repositories where PRs may
come from untrusted sources -- such as a coding agent like
[Airut](https://github.com/airutorg/airut).

Standard GitHub Actions runners give workflow steps full outbound network access
and expose repository secrets as environment variables. This means a malicious
PR that modifies test scripts or build steps can exfiltrate secrets to an
external server. Sandbox Action prevents this by:

- **Restricting network access** to an allowlist of permitted hosts and paths
- **Masking credentials** with surrogate values that the network proxy swaps for
  real secrets only on matching outbound requests, so the code inside the
  container never sees real credential values
- **Isolating execution** in a container with `--cap-drop=ALL` and
  `no-new-privileges`

## Quick Start

> **Before using this action, you MUST ensure all three security requirements
> are met. Failure to do so undermines the sandbox and may expose secrets.**
>
> 1. **Restrict workflow file modifications.** The token used to push branches
>    must lack the `workflow` scope, or a repository ruleset must prevent
>    modifications to `.github/workflows/`. Otherwise, untrusted code can push a
>    workflow that runs outside the sandbox.
>
> 1. **Protect the base branch and restrict the workflow trigger.** The workflow
>    must trigger only on PRs targeting a protected branch (e.g.,
>    `branches: [main]`). Sandbox configuration is loaded from the base branch;
>    if the base branch is unprotected, a PR author could push malicious
>    configuration to it.
>
> 1. **Do not add steps after this action.** After sandbox execution, the
>    workspace is tainted -- untrusted code had write access to `.git/` and all
>    files. Any subsequent step (git commands, artifact uploads, scripts) risks
>    executing attacker-controlled code outside the sandbox.

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
    branches: [main]  # MUST target only protected branches

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      # This must be the ONLY step -- nothing after it
      - uses: airutorg/sandbox-action@v0
        with:
          command: 'uv sync && uv run pytest'
          pr_sha: ${{ github.event.pull_request.head.sha }}
```

## What It Does

1. Installs `uv`, Python, and `airut-sandbox` on the host
1. Checks out the **base branch** (trusted sandbox configuration)
1. Fetches the PR commit on the host (no GitHub credentials needed in sandbox)
1. Restores cached container images (or builds and caches them on first run)
1. Runs your command inside `airut-sandbox`: container isolation, network
   allowlisting, and **masked credentials** (surrogate tokens that the proxy
   replaces with real values only on matching outbound requests)

The PR code runs **only inside the container**. Sandbox configuration
(`.airut/sandbox.yaml`, `.airut/container/Dockerfile`,
`.airut/network-allowlist.yaml`) always comes from the trusted base branch.

## Inputs

| Input           | Required | Default        | Description                                                               |
| --------------- | -------- | -------------- | ------------------------------------------------------------------------- |
| `command`       | Yes      |                | CI command to run inside the sandbox (after PR checkout)                  |
| `pr_sha`        | Yes      |                | PR commit SHA to check out and test                                       |
| `merge`         | No       | `true`         | Merge PR into base branch before running (like GitHub's default behavior) |
| `airut_version` | No       | from `VERSION` | Airut version (`0.15.0` for PyPI, `main` for GitHub HEAD)                 |
| `sandbox_args`  | No       | `--verbose`    | Additional arguments for `airut-sandbox run`                              |
| `cache`         | No       | `true`         | Enable image caching across CI runs                                       |
| `cache-version` | No       | `""`           | Arbitrary string to force cache invalidation                              |
| `cache-max-age` | No       | `168`          | Maximum image age (hours) before forced rebuild                           |

When `merge` is `true` (the default), the container starts on the base branch
and runs `git merge --no-edit <sha>` to create a temporary merge commit. This
matches GitHub Actions' default `pull_request` checkout behavior and tests the
code as it would exist after merging. Set to `false` to check out the PR commit
directly instead.

## Prerequisites

Your repository needs:

- `.airut/container/Dockerfile` -- container image (Python, uv, tools)
- `.airut/sandbox.yaml` (optional) -- env vars, masked secrets, resource limits
- `.airut/network-allowlist.yaml` (optional) -- required if
  `network_sandbox: true`

The network allowlist does **not** need to include your repository's GitHub URL.
The action fetches the PR SHA on the host before entering the sandbox.

## Configuration

### Sandbox Config (`.airut/sandbox.yaml`)

This file controls what the container receives. It lives on the default branch
and is reviewed by humans before taking effect.

```yaml
# .airut/sandbox.yaml

# Environment variables (non-sensitive only)
env:
  CI: "true"
  PYTHONDONTWRITEBYTECODE: "1"

# Network sandbox (enabled by default)
network_sandbox: true

# Masked secrets — container gets surrogates, proxy swaps for real values
# only on matching hosts. Prevents credential exfiltration.
masked_secrets:
  GH_TOKEN:
    value: !env GH_TOKEN
    scopes: ["api.github.com", "*.githubusercontent.com"]
    headers: ["Authorization"]

# Resource limits
resource_limits:
  memory: "4g"
  cpus: 2
  timeout: 600
```

Pass secrets from GitHub Actions via `env:` on the action step:

```yaml
- uses: airutorg/sandbox-action@v0
  with:
    command: 'uv sync && uv run pytest'
    pr_sha: ${{ github.event.pull_request.head.sha }}
  env:
    GH_TOKEN: ${{ secrets.GH_TOKEN }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The `!env` tags in `sandbox.yaml` resolve from the runner's environment
variables (set by the workflow `env:` block). If a referenced variable is
missing, `airut-sandbox` exits with code 125 (fail-closed).

### Credential Handling

The credential mechanism is determined by what the target service supports:

| Mechanism               | When to use                                | How it works                                                                |
| ----------------------- | ------------------------------------------ | --------------------------------------------------------------------------- |
| **Signing credentials** | AWS services that use SigV4/SigV4A         | Proxy re-signs requests; real keys never enter container                    |
| **Masked secrets**      | Token-based APIs (GitHub, Anthropic, etc.) | Container sees surrogates; proxy swaps for real values on matching requests |
| **`pass_env`**          | Non-sensitive values (CI flags, locale)    | Real value visible inside container                                         |

**Masked secrets should be the default for all credentials.** SigV4 signing
credentials are only applicable to AWS services and cannot be used elsewhere.
SigV4 has the additional property that real keys never leave the server
configuration and proxy container, but the choice between the two mechanisms is
driven by what the service supports, not by a security preference.

### Network Allowlist

If `network_sandbox: true` (the default), the container's outbound HTTP(S)
traffic is restricted to `.airut/network-allowlist.yaml`. The allowlist does
**not** need to include the repository's own GitHub URL -- the action fetches
the PR SHA on the host before entering the sandbox.

See the Airut
[network sandbox documentation](https://github.com/airutorg/airut/blob/main/doc/network-sandbox.md)
for the allowlist format and examples.

## Full Workflow Example

```yaml
name: CI
on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: airutorg/sandbox-action@v0
        with:
          command: |
            uv sync
            uv run scripts/ci.py --verbose --timeout 0
          pr_sha: ${{ github.event.pull_request.head.sha || github.sha }}
          sandbox_args: '--verbose'
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Runner Requirements

- **Container runtime**: podman (included on GitHub-hosted `ubuntu-latest`) or
  docker
- **Network**: host needs internet for checkout, uv install, and image builds

## Security Model

The base branch is trusted. Sandbox configuration (Dockerfile, network
allowlist, masked secret definitions, resource limits) is loaded from the base
branch checkout on the host. The PR is untrusted -- it runs inside the sandbox
where network access is restricted and credentials are masked.

This requires two external controls that the action cannot enforce itself:

1. **Workflow files must be immutable to the PR author.** The push token must
   lack the `workflow` scope, or a repository ruleset must block changes to
   `.github/workflows/`. Without this, the PR author can push a workflow that
   bypasses the sandbox entirely.

1. **The base branch must be protected, and the workflow must only trigger on
   PRs targeting protected branches.** If the workflow triggers on PRs to
   unprotected branches, the PR author can push malicious `.airut/` config to
   the base branch before the workflow runs.

The action is fail-secure: if any setup step fails (installation error, missing
container runtime, fetch failure), the workflow exits non-zero. There is no
fallback to unsandboxed execution.

For the full trust model, detailed security requirements (PAT scope
configuration, branch protection setup, push rulesets), and residual risk
analysis, see the Airut
[CI sandbox security guide](https://github.com/airutorg/airut/blob/main/doc/ci-sandbox.md).

### Tainted Workspace

**This action must be the last step in the job.** After sandbox execution, the
workspace is tainted -- untrusted PR code had write access to all files
including `.git/`. A malicious PR could install git hooks, modify `.git/config`,
or replace binaries. Any subsequent workflow step that touches the workspace or
runs git commands risks executing attacker-controlled code outside the sandbox.

If post-sandbox operations are needed (e.g., uploading test artifacts), they
must run in a separate job that does not share the tainted workspace.

## Image Caching

By default, the action caches built container images across CI runs using
`actions/cache`. This eliminates redundant image builds on ephemeral runners,
saving ~50 s per CI run.

Two images are cached independently:

- **Repo image**: Your tools and dependencies. Cache key includes the Dockerfile
  content hash.
- **Proxy image**: The network sandbox proxy. Cache key includes a hash of the
  proxy package files.

All cache operations run **before** the sandbox executes untrusted code. No
steps run after the sandbox. Cache keys are content-addressed, so cached images
are always consistent with the current configuration.

To disable caching (e.g., for debugging image builds):

```yaml
- uses: airutorg/sandbox-action@v0
  with:
    command: 'uv sync && uv run pytest'
    pr_sha: ${{ github.event.pull_request.head.sha }}
    cache: 'false'
```

To force cache invalidation (e.g., after urgent security patches), bump
`cache-version`:

```yaml
- uses: airutorg/sandbox-action@v0
  with:
    command: 'uv sync && uv run pytest'
    pr_sha: ${{ github.event.pull_request.head.sha }}
    cache-version: '2'
```

## Debugging Network Issues

When a sandboxed CI command fails due to blocked network requests, use the
`sandbox_args` input to enable live network logging. This streams every DNS
query, allowed request, and blocked request to the job log in real time:

```yaml
- uses: airutorg/sandbox-action@v0
  with:
    command: 'uv sync && uv run pytest'
    pr_sha: ${{ github.event.pull_request.head.sha }}
    sandbox_args: '--verbose --network-log-live'
```

The `--network-log-live` flag prints each network event to stderr as it happens,
prefixed with `[net]`:

```
[net] DNS A pypi.org -> 10.199.1.100
[net] allowed GET https://pypi.org/simple/requests/ -> 200
[net] BLOCKED GET https://evil.com/exfiltrate -> 403
```

You can also save the full network log to a file for later inspection (e.g., as
a CI artifact) by adding `--network-log`:

```yaml
- uses: airutorg/sandbox-action@v0
  with:
    command: 'uv sync && uv run pytest'
    pr_sha: ${{ github.event.pull_request.head.sha }}
    sandbox_args: '--verbose --network-log-live --network-log /tmp/network.log'
```

**Available network debugging flags** (passed via `sandbox_args`):

| Flag                 | Effect                                             |
| -------------------- | -------------------------------------------------- |
| `--network-log-live` | Stream network activity to stderr during execution |
| `--network-log FILE` | Save network activity log to FILE                  |
| `--verbose`          | Enable INFO-level sandbox logging                  |
| `--debug`            | Enable DEBUG-level logging (implies `--verbose`)   |

The default `sandbox_args` is `--verbose`. When you override it, include
`--verbose` explicitly if you still want sandbox-level informational logs
alongside the network log.

## Versioning

| Ref        | Installs from             | Use case    |
| ---------- | ------------------------- | ----------- |
| `@v0`      | PyPI (latest 0.x.y)       | Stable      |
| `@v0.15.0` | PyPI (`airut==0.15.0`)    | Pinned      |
| `@main`    | GitHub (airut repo, HEAD) | Development |
