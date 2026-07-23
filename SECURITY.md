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

Jarvis-os reads Docker state through the Docker socket. Docker socket access is highly privileged, even when mounted read-only.

Only run Jarvis-os on trusted hosts and trusted networks. Anyone who can access a service with Docker socket access may gain sensitive information about the host and workloads.

The normal Jarvis application and staging container must never receive a Docker socket mount. The existing read-only monitoring proxy is not an installation API and cannot create or modify containers.

## Managed Home Assistant installer boundary

The managed Home Assistant foundation creates a plan only. It does not run Docker, subprocesses or shell commands.

Any future installation execution must be a separate, one-shot component that:

- starts only after an explicit owner confirmation and exits after the task
- accepts no browser-provided image, resource name, port, path or command
- uses only the fixed `jarvis-managed-home-assistant` container, volume and network namespace
- implements only its documented allowlisted operations
- never adopts, inspects, stops, restarts, removes or modifies unrelated resources
- never exposes a generic Docker API

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
