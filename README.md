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
>    modifications to `.github/workflows/`. Otherwise, untrusted code can
>    push a workflow that runs outside the sandbox.
>
> 2. **Protect the base branch and restrict the workflow trigger.** The
>    workflow must trigger only on PRs targeting a protected branch (e.g.,
>    `branches: [main]`). Sandbox configuration is loaded from the base
>    branch; if the base branch is unprotected, a PR author could push
>    malicious configuration to it.
>
> 3. **Do not add steps after this action.** After sandbox execution, the
>    workspace is tainted -- untrusted code had write access to `.git/` and
>    all files. Any subsequent step (git commands, artifact uploads, scripts)
>    risks executing attacker-controlled code outside the sandbox.

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
2. Checks out the **base branch** (trusted sandbox configuration)
3. Fetches the PR commit on the host (no GitHub credentials needed in sandbox)
4. Runs your command inside `airut-sandbox`: container isolation, network
   allowlisting, and **masked credentials** (surrogate tokens that the proxy
   replaces with real values only on matching outbound requests)

The PR code runs **only inside the container**. Sandbox configuration
(`.airut/sandbox.yaml`, `.airut/container/Dockerfile`,
`.airut/network-allowlist.yaml`) always comes from the trusted base branch.

## Inputs

| Input              | Required | Default        | Description                                                                |
| ------------------ | -------- | -------------- | -------------------------------------------------------------------------- |
| `command`          | Yes      |                | CI command to run inside the sandbox (after PR checkout)                   |
| `pr_sha`           | Yes      |                | PR commit SHA to check out and test                                        |
| `merge`            | No       | `true`         | Merge PR into base branch before running (like GitHub's default behavior) |
| `airut_version`    | No       | from `VERSION` | Airut version (`0.15.0` for PyPI, `main` for GitHub HEAD)                 |
| `sandbox_args`     | No       | `--verbose`    | Additional arguments for `airut-sandbox run`                               |
| `network_log_live` | No       | `false`        | Print network activity to the job log (useful for diagnosing sandbox issues) |

When `merge` is `true` (the default), the container starts on the base branch
and runs `git merge --no-edit <sha>` to create a temporary merge commit. This
matches GitHub Actions' default `pull_request` checkout behavior and tests the
code as it would exist after merging. Set to `false` to check out the PR commit
directly instead.

## Prerequisites

Your repository needs:

- `.airut/container/Dockerfile` -- container image (Python, uv, tools)
- `.airut/sandbox.yaml` (optional) -- env vars, masked secrets, resource limits
- `.airut/network-allowlist.yaml` (optional) -- required if `network_sandbox:
  true`

The network allowlist does **not** need to include your repository's GitHub URL.
The action fetches the PR SHA on the host before entering the sandbox.

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

2. **The base branch must be protected, and the workflow must only trigger on
   PRs targeting protected branches.** If the workflow triggers on PRs to
   unprotected branches, the PR author can push malicious `.airut/` config to
   the base branch before the workflow runs.

The action is fail-secure: if any setup step fails (installation error, missing
container runtime, fetch failure), the workflow exits non-zero. There is no
fallback to unsandboxed execution.

### Tainted Workspace

**This action must be the last step in the job.** After sandbox execution, the
workspace is tainted -- untrusted PR code had write access to all files
including `.git/`. A malicious PR could install git hooks, modify `.git/config`,
or replace binaries. Any subsequent workflow step that touches the workspace or
runs git commands risks executing attacker-controlled code outside the sandbox.

If post-sandbox operations are needed (e.g., uploading test artifacts), they
must run in a separate job that does not share the tainted workspace.

## Versioning

| Ref        | Installs from             | Use case    |
| ---------- | ------------------------- | ----------- |
| `@v0`      | PyPI (latest 0.x.y)      | Stable      |
| `@v0.15.0` | PyPI (`airut==0.15.0`)   | Pinned      |
| `@main`    | GitHub (airut repo, HEAD) | Development |
