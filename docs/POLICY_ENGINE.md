# Jarvis-os Policy Engine

The Policy Engine is the first safety decision layer for Jarvis-os. It makes Jarvis explain what it may do, what it must not do, and why.

## Why policies exist

Jarvis should not make decisions through scattered hardcoded logic. Policies give the system a single explainable place for decision-making.

A policy can answer:

- What matched
- Why it matched
- What action was allowed
- What action was denied
- Which rule caused the decision
- Whether the decision was dry-run only

The current Policy Engine is intentionally conservative. It can create incidents and recommendations, but it does not automatically restart containers.

## Decision flow

Typical flow:

```text
DockerPlugin
↓
Event Engine
↓
Policy Engine listener
↓
Policy match + conditions
↓
Decision stored in SQLite
↓
Allowed safe side effects only: incident/recommendation/ignore/deny
↓
Mission Control
```

## Policy model

Each policy contains:

- `policy_id`
- `name`
- `description`
- `enabled`
- `priority`
- `trigger_event_type`
- `conditions`
- `actions`
- `safety_level`
- `created_at`
- `updated_at`

Policies are stored in SQLite in the `policies` table.

## Decision model

Each policy decision contains:

- `decision_id`
- `policy_id`
- `timestamp`
- `asset_id`
- `event_id`
- `matched`
- `allowed`
- `action`
- `reason`
- `explanation`
- `dry_run`

Decisions are stored in SQLite in `policy_decisions`.

## Default policies

### Unknown container discovered

Trigger: `Docker.ContainerUnknown`

Condition: `classification == unknown`

Action: create a recommendation to classify the asset. No automatic action.

### Critical Docker container stopped

Trigger: `Docker.ContainerStopped`

Condition: `classification == critical`

Action: create a critical incident and recommendation. No auto restart by default.

### Optional Docker container stopped

Trigger: `Docker.ContainerStopped`

Condition: `classification == optional`

Action: create a recommendation to restart manually. No auto restart by default.

### Stopped-by-design container stopped

Trigger: `Docker.ContainerStopped`

Condition: `classification == stopped_by_design`

Action: ignore with an explanation. No recommendation.

### qBittorrent dependency guard

Trigger: `Docker.*`

Condition: `asset_id == docker:qbittorrent`

Dependency: `docker:gluetun` must be `running` before any future qBittorrent start action is allowed.

Action: deny unsafe auto-start if the dependency is not running. It does not execute any action.

## Safety model

The Policy Engine is allowed to:

- Evaluate events
- Read assets
- Read relationships
- Store decisions
- Create recommendations
- Create incidents
- Deny or ignore actions with explanation

It is not allowed to:

- Execute arbitrary shell commands
- Delete files
- Delete Docker volumes
- Run Docker prune
- Change firewall rules
- Change DNS settings
- Change Docker volumes
- Perform destructive automatic actions
- Let AI execute actions directly

AI can suggest or explain. It cannot bypass policies.

## API

Policy endpoints:

- `GET /api/policies`
- `GET /api/policies/{policy_id}`
- `POST /api/policies/{policy_id}/enable`
- `POST /api/policies/{policy_id}/disable`
- `GET /api/policy-decisions`
- `GET /api/policy-decisions/latest`

## Future YAML/rules support

The current rules are Python-defined defaults persisted to SQLite. A future version can add YAML-backed rules or UI editing, but the same safety model should remain:

1. Policy conditions must match.
2. Safety must approve the action.
3. Decisions must be stored.
4. Actions must be explainable.
5. AI cannot bypass the policy layer.

## Relationship to Event Engine and Asset Registry

The Policy Engine listens to Event Engine events and uses `asset_id` to look up current Asset Registry state.

This keeps future integrations plugin-neutral. Home Assistant, UniFi, AdGuard, UPS, Tailscale, Calendar, Notifications and LLM reasoning can publish events and register assets without changing the policy core.
