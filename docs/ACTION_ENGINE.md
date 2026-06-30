# Jarvis-os Action Engine

The Action Engine is the safe execution boundary for Jarvis-os.

Policies and AI may recommend, queue, explain or request actions, but they must never execute actions directly.

## Why actions are separate from policies

Policies decide what may be considered. Actions handle execution safely.

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

This separation keeps Jarvis explainable and prevents policy logic, AI logic or UI logic from directly touching Docker or future integrations.

## Supported actions

Supported action types in this branch:

- `docker.start_container`
- `recommendation.create`
- `incident.create`
- `notification.create_stub`

Only `docker.start_container` touches Docker. It uses the Docker SDK only.

Unsupported action categories include stopping, deleting, pruning, command execution, compose control, file deletion, volume changes, firewall changes and DNS changes.

## Action model

Each action contains identifiers, timestamps, requester, source, asset, action type, status, approval fields, safety status, reason, explanation, payload and result.

Statuses:

- `queued`
- `waiting_approval`
- `approved`
- `running`
- `completed`
- `failed`
- `denied`
- `cancelled`

Actions are stored in SQLite and survive container restart.

## Manual approval flow

1. User or policy queues an action.
2. The action is stored as `waiting_approval` when approval is required.
3. User approves the action.
4. User runs the action.
5. Safety checks run immediately before execution.
6. Executor runs only if safety passes.
7. Verification reads live state again.
8. Result and explanation are stored.

Mission Control exposes approve, deny, cancel and run controls.

## Docker start safety rules

`docker.start_container` is allowed only when all are true:

- `SAFE_MODE=true`
- Asset exists
- Asset type is `docker_container`
- Asset state is `exited`
- Asset is not protected
- Asset classification is `optional`
- Asset is not `unknown`
- Manual approval is present, unless `auto_actions_allowed=true`
- Dependency guards pass
- Action type is not destructive

Protected assets cannot be started by the Action Engine.

Unknown assets cannot receive restart/start actions.

Dependency guards are relationship-driven. For example, a future plugin or local configuration may define that one Docker asset depends on another Docker asset and require the dependency to be running before a start action can pass.

## Verification

After Docker start, Jarvis re-reads live Docker state through the existing Docker monitor.

The action only becomes `completed` if verification confirms the asset is `running`.

If verification fails, the action becomes `failed` and stores the reason.

## AI safety boundary

AI cannot execute actions directly.

AI may explain, suggest, or request that an action be queued. AI may not bypass policy decisions, manual approval, safety checks or verification.

## API

Action endpoints:

- `GET /api/actions`
- `GET /api/actions/{action_id}`
- `POST /api/actions/queue`
- `POST /api/actions/{action_id}/approve`
- `POST /api/actions/{action_id}/deny`
- `POST /api/actions/{action_id}/cancel`
- `POST /api/actions/{action_id}/run`

Legacy action log is available at:

- `GET /api/action-log`

## Future action types

Future safe action types can be added behind the same boundary:

- Home automation service request with policy constraints
- Network-controller remediation suggestion
- DNS-filter list update request with approval
- Notification delivery
- Backup verification
- UPS shutdown recommendation

Any future executor must declare safety rules, verification and forbidden operations before it is enabled.
