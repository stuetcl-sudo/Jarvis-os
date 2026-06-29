# Jarvis-os Action Engine

The Action Engine is the safe execution layer for Jarvis-os. It separates decisions from execution so AI and policies cannot run actions directly.

## Why actions are separate from policies

The Policy Engine decides what is allowed or recommended. The Action Engine handles the actual lifecycle of an action.

Flow:

```text
Policy Decision
↓
Action Queue
↓
Safety Check
↓
Executor
↓
Verification
↓
Action History
↓
Explanation
```

Policies may create queued actions, but they cannot run them. AI may suggest or explain, but it cannot execute actions directly.

## Action model

Each action contains:

- `action_id`
- `created_at`
- `updated_at`
- `requested_by`
- `source`
- `asset_id`
- `action_type`
- `status`
- `priority`
- `requires_approval`
- `approved`
- `approved_by`
- `approved_at`
- `safety_status`
- `reason`
- `explanation`
- `payload`
- `result`

Statuses:

- `queued`
- `waiting_approval`
- `approved`
- `running`
- `completed`
- `failed`
- `denied`
- `cancelled`

Actions are stored in SQLite in the `actions` table and survive container restart.

## Manual approval flow

1. A user or policy queues an action.
2. If approval is required, the action enters `waiting_approval`.
3. A user approves or denies it.
4. A user runs it.
5. The Action Engine performs safety checks.
6. The executor runs only if safety passes.
7. Verification confirms the result.
8. The action is stored with explanation and result.

## Supported v0.7 actions

- `docker.start_container`
- `recommendation.create`
- `incident.create`
- `notification.create_stub`

No other executor exists in v0.7.

## Docker start safety rules

`docker.start_container` is allowed only when all checks pass:

- `SAFE_MODE=true`
- Asset exists
- Asset type is `docker_container`
- Asset state is `exited`
- Asset is not protected
- Asset classification is `optional`
- Asset is not unknown
- Action type is allowed
- Policy decision allows it when action source is policy
- Manual approval is present when required
- Dependency guards pass
- Action is not destructive

Protected assets cannot receive restart/start actions. Unknown assets cannot receive automatic or queued restart actions.

## Docker executor

The Docker executor supports only `docker.start_container`.

It uses the Docker SDK to:

1. Read the container state.
2. Confirm it is `exited`.
3. Start the container.
4. Verify by re-reading live Docker state.
5. Publish `Action.Completed` or `Action.Failed`.
6. Store result and explanation.

It does not implement stop, delete, prune, exec, update, compose or shell.

## API

- `GET /api/actions`
- `GET /api/actions/{action_id}`
- `POST /api/actions/queue`
- `POST /api/actions/{action_id}/approve`
- `POST /api/actions/{action_id}/deny`
- `POST /api/actions/{action_id}/cancel`
- `POST /api/actions/{action_id}/run`

Queue request example:

```json
{
  "asset_id": "docker:jellyfin",
  "action_type": "docker.start_container",
  "requested_by": "user",
  "reason": "manual restart from Mission Control",
  "requires_approval": true
}
```

## Safety model

The Action Engine must not:

- Execute arbitrary shell commands
- Delete files
- Delete Docker volumes
- Run Docker prune
- Change firewall rules
- Change DNS settings
- Change Docker volumes
- Add destructive automatic actions
- Let AI execute actions directly

Every action must be explainable and traceable.

## Future action types

Future versions may add more action types, but each must be explicitly added to the allowed action list, have a narrow executor, pass safety checks, and produce verification plus history.

Possible future actions:

- Home Assistant service call with allowlist
- UniFi read-only diagnostics
- AdGuard safe list reload
- UPS notification
- Tailscale status alert
- Notification delivery

The core rule remains: policy decides, Action Engine safely executes, AI never bypasses the queue.
