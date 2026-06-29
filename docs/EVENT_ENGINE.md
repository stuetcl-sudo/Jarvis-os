# Jarvis-os Event Engine

The Event Engine turns Jarvis-os into an event-driven platform while keeping the v0.3 APIs and safety model intact.

## Event flow

Typical flow:

```text
Docker Plugin
↓
Docker.ContainerStopped event
↓
Event Bus
↓
Policy / Safety checks
↓
Memory and recommendations
↓
Mission Control UI
```

Every event contains:

- `id`
- `timestamp`
- `source`
- `type`
- `severity`
- `service`
- `payload`

Example event types:

- `Docker.ContainerStopped`
- `Docker.ContainerStarted`
- `Docker.Collected`
- `System.HealthCollected`
- `System.HighRAM`
- `System.HighSwap`
- `System.HighCPU`
- `Recommendation.Created`
- `Worker.Started`
- `Worker.Completed`

## Event Bus

The Event Bus provides:

- `publish(event)`
- `subscribe(event_type, listener)`
- `unsubscribe(event_type, listener)`
- `history(limit)`

Listeners can subscribe to a specific event type or to `*` for all events. Listener failures are isolated so one bad listener cannot crash the worker.

## Worker flow

The worker now publishes events during checks:

1. `Worker.Started`
2. Docker collection events from DockerPlugin
3. `System.HealthCollected`
4. High resource events when thresholds are crossed
5. Memory and recommendation flow
6. `Worker.Completed` or `Worker.Failed`

Existing worker behavior is preserved. The worker still runs every 60 seconds and continues after exceptions.

## Plugin flow

Plugins inherit from `PluginBase` and may implement:

- `initialize()`
- `shutdown()`
- `register()`
- `on_event(event)`
- `publish(...)`
- `collect()`

Plugins are not allowed to execute arbitrary system commands directly. The first plugin direction is read-only collection and event publication.

## Memory integration

Important events are stored in SQLite in the `events` table. Jarvis keeps the latest 10,000 events and removes older event rows from its own database table only.

This does not delete files, Docker data, Docker volumes or external data.

## API

Event endpoints:

- `GET /api/events`
- `GET /api/events/latest`
- `GET /api/events/types`
- `GET /api/events/statistics`

## Mission Control

Mission Control shows a live event feed with newest events first. Events are displayed with severity, source, service and timestamp.

## Future integrations

The Event Engine is designed so future integrations can publish and subscribe to events without changing the core:

- Home Assistant
- UniFi
- AdGuard
- Notifications
- LLM / local assistant reasoning

## Safety boundaries

Jarvis must not:

- Execute arbitrary shell commands
- Delete files
- Delete Docker volumes
- Run Docker prune
- Change firewall rules
- Change DNS settings
- Change Docker volumes
- Add destructive automatic actions

The Event Engine does not weaken these rules. Events describe facts and intent; actions still need explicit policy and safety checks.
