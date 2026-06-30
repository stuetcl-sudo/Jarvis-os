# Jarvis-os Asset Registry

The Asset Registry is the foundation for Jarvis-os becoming a local digital twin of the observed environment.

## What is an Asset

An Asset is anything Jarvis can observe, reason about, show in Mission Control or eventually manage through explicit safe policies.

Generic examples:

- `docker:example-app`
- `docker:database`
- `docker:reverse-proxy`
- `system:cpu`
- `system:memory`
- `system:disk`
- `plugin:example-device`

Each asset contains:

- `asset_id`
- `asset_type`
- `plugin`
- `name`
- `display_name`
- `state`
- `health`
- `classification`
- `protected`
- `auto_actions_allowed`
- `metadata`
- `created_at`
- `updated_at`

Assets are persisted in SQLite so they survive container restarts.

## Asset Registry

The registry supports:

- `register_asset()`
- `update_asset()`
- `remove_asset()`
- `get_asset()`
- `list_assets()`
- `search_assets()`

The registry is plugin-neutral. Future plugins should register assets without changing the registry schema or core APIs.

## Relationship Engine

The relationship engine stores links between assets.

Supported relationships:

- `depends_on`
- `contains`
- `connected_to`
- `managed_by`
- `hosted_on`

Generic examples:

```text
docker:example-app depends_on docker:database
system:docker contains docker:example-app
docker:worker depends_on docker:example-queue
```

Docker containers always receive the generic relationship:

```text
system:docker contains docker:<container-name>
```

Other dependencies must come from configuration, labels, plugin metadata or future policy configuration.

Relationships are also persisted in SQLite.

## Plugin interaction

Plugins observe external systems and convert what they see into assets.

Current Docker flow:

```text
DockerPlugin
↓
Read live Docker Engine state
↓
Register/update docker:<container> assets
↓
Create generic relationship to system:docker
↓
Publish events referencing asset_id
↓
Mission Control shows assets, events and relationships
```

Plugins must not execute arbitrary system commands directly. The first design goal is safe observation and explicit policy-controlled actions.

## Event integration

Events now reference `asset_id` where possible.

Example:

```json
{
  "source": "docker",
  "type": "Docker.ContainerStopped",
  "service": "docker:example-app",
  "asset_id": "docker:example-app",
  "payload": {
    "asset_id": "docker:example-app"
  }
}
```

The `service` field remains for backward compatibility, but it should contain the asset ID for new event-driven flows.

## API

Asset endpoints:

- `GET /api/assets`
- `GET /api/assets/{id}`
- `GET /api/assets/search?q=...`
- `GET /api/assets/relationships`

Existing APIs remain available.

## Future Digital Twin

The Asset Registry is designed for future plugins without changing the core. Product-specific integrations should remain optional plugins with explicit safety boundaries.

The long-term direction is a local digital twin where Jarvis can answer questions such as:

- What depends on this network-facing container?
- Which services are hosted on Docker?
- Which entities belong to a room or zone?
- Which devices are connected to which network asset?

## Safety boundaries

The Asset Registry does not grant permission to act. It only models what Jarvis knows.

Jarvis must not:

- Execute arbitrary shell commands
- Delete files
- Delete Docker volumes
- Run Docker prune
- Change firewall rules
- Change DNS settings
- Change Docker volumes
- Perform destructive automatic actions

Future actions must go through explicit safety and policy layers.
