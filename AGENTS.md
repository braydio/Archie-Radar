# Repository Instructions

## Commit and push every change

This repository is deployed directly from `main`.

For every agent run that changes repository files:

1. Work against the latest `main`.
2. Before editing, inspect and synchronize safely:
   ```bash
   git status --short
   git branch --show-current
   git checkout main
   git pull --ff-only origin main
   ```
3. Preserve unrelated user changes. Do not reset, clean, discard, or overwrite work that was not created by the current task.
4. Make the requested changes and run focused checks appropriate to the files changed. Avoid expensive full-suite testing unless the task specifically requires it.
5. Commit all intended changes to `main` with a descriptive commit message.
6. Push the commit before finishing:
   ```bash
   git push origin main
   ```
7. Verify that `origin/main` points to the pushed commit.
8. Do not leave completed implementation changes only in a local worktree or feature branch. If the task made no repository changes, do not create an empty commit.

Never force-push. If `main` advances, integrate the new remote changes safely before pushing.

Use the current system user's normal Git/SSH configuration and SSH agent. Do not copy, print, replace, or hard-code private keys. Never add private keys, tokens, cookies, Facebook storage state, `.env`, or other secrets to Git.

## Deploy every pushed change to DietPi

After every successful push to `origin/main`, deploy that exact revision to the Tailscale-connected DietPi host **only when the current execution environment actually has SSH/Tailscale access to that device**. If the environment cannot reach the device, skip deployment, report that it was not attempted from this environment, and do not treat that limitation as a repository-task failure.

### SSH rules

- First verify that an SSH client is available and that this execution environment is permitted to reach the Tailscale host. Do not install or bootstrap SSH/Tailscale just to satisfy this section.
- When access is available, SSH to the Tailscale host named `dietpi` as the current system user:
  ```bash
  ssh dietpi
  ```
- Use the current system user's existing SSH keys/configuration. Do not specify, generate, copy, expose, or replace SSH key material unless the user explicitly asks.
- Do not require the user's ordinary desktop browser to remain open.

### Use the existing remote checkout

Use the existing Archie Radar checkout on `dietpi`. Do not clone a second deployment copy simply because the path is not initially known.

If the checkout path is not already known, locate the existing repository and verify its origin before making deployment changes:

```bash
git -C /path/to/repo remote get-url origin
```

The origin must correspond to `braydio/Archie-Radar`.

If the remote checkout contains unexpected local modifications, stop and report them rather than resetting or overwriting them.

### Pull main and restart the running app

From the existing Archie Radar repository on `dietpi`:

```bash
git status --short
git checkout main
git pull --ff-only origin main
docker compose up -d --build --remove-orphans
docker compose ps
```

Requirements:

- The remote checkout must end on `main`.
- Pull with `git pull --ff-only origin main`; never force-reset the remote deployment checkout.
- Rebuild/recreate the Archie Radar Docker Compose services with `docker compose up -d --build --remove-orphans` so code and dependency changes take effect.
- Verify the running services with `docker compose ps`.
- Never run `docker compose down -v`, `docker volume rm`, or otherwise remove the persistent Archie Radar data volume during routine deployment.
- Never delete the SQLite database, media volume, Facebook session state, or other persistent runtime data.

### Lightweight deployment verification

After restart, perform a lightweight verification appropriate to the change. At minimum:

```bash
docker compose ps
```

When practical, also verify the service responds locally from `dietpi`. Use the live Compose/`.env` port configuration rather than assuming the API host port is always the repository default.

If deployment fails:

1. Do not destroy volumes or reset persistent data.
2. Capture `docker compose ps` and only the relevant bounded service logs.
3. Fix the issue in the repository when appropriate.
4. Commit and push the fix to `main`.
5. Pull `main` on `dietpi` again and restart the Compose services.
6. Report any failure that cannot be resolved safely.

## End-of-run report

For every repository-changing run, report:

- commit SHA pushed to `main`
- whether `dietpi` pulled that SHA
- Docker Compose restart result
- lightweight verification result
- any blocker or dirty-worktree condition

If this environment has no device access, report `DietPi deployment: not attempted from this environment` and stop there. Do not simulate the remote commands, do not claim failure, and do not claim deployment succeeded.

When device access is available, do not claim deployment succeeded unless the remote pull and Docker Compose restart were actually executed successfully.
