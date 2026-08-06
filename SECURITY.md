# Security Policy

## Security status

Jarvis-os currently has no built-in authentication.

Do not expose port `8088` directly to the public internet.

Recommended access patterns:

- Trusted LAN only
- Tailscale or another trusted private network
- Authenticated reverse proxy

## Secrets and private data

Never commit:

- `.env`
- SQLite databases
- Logs
- API tokens
- Passwords
- SSH keys
- Screenshots containing infrastructure details
- Docker inventories
- Private hostnames
- Real IP addresses

Use placeholders such as `example.com`, `docker:example-app`, `system:cpu`, and documentation IP ranges when writing examples.

## Docker socket warning

The normal Jarvis service and staging never receive the raw Docker socket. Managed Home Assistant installation is an explicit one-shot operation. After installation, `compose.managed-home-assistant.yml` may be enabled to attach Jarvis to the dedicated external managed network; this grants network connectivity to the fixed managed Home Assistant container but no additional Docker API access.

Jarvis-os reads Docker state through the Docker socket. Docker socket access is highly privileged, even when mounted read-only.

Only run Jarvis-os on trusted hosts and trusted networks. Anyone who can access a service with Docker socket access may gain sensitive information about the host and workloads.

The normal Jarvis application and staging container must never receive a Docker socket mount. The existing read-only monitoring proxy is not an installation API and cannot create or modify containers.

## Managed Home Assistant installer boundary

The daily application creates a plan and an expiring, single-use opaque installation request only. It does not run Docker, subprocesses or shell commands.

Installation execution is the opt-in `compose.installer.yml` one-shot component. It:

- starts only after an explicit owner confirmation and exits after the task
- accepts no browser-provided image, resource name, port, path or command
- uses only the fixed `jarvis-managed-home-assistant` container, volume and network namespace
- implements only its documented allowlisted operations
- never adopts, inspects, stops, restarts, removes or modifies unrelated resources
- never exposes a generic Docker API

Only that one-shot installer component mounts `/var/run/docker.sock` with write access; it exposes no port and receives no application secrets. Its request expires after ten minutes, is atomically consumed once, and cannot carry Docker arguments. Conflicting fixed-name resources are refused rather than adopted. The normal Jarvis application and staging remain raw-socket-free, and staging never runs the installer.

Staging remains isolated and must not use the real Docker socket.

## Vulnerability reporting

Do not publish security vulnerabilities as public issues before maintainers have had a chance to review and respond privately.

If you discover a vulnerability, contact the repository maintainers privately first with:

- A clear description
- Affected version or branch
- Reproduction steps
- Impact assessment
- Suggested fix, if available

Maintainers should acknowledge receipt and coordinate responsible disclosure before public details are posted.
