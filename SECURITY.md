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

## Vulnerability reporting

Do not publish security vulnerabilities as public issues before maintainers have had a chance to review and respond privately.

If you discover a vulnerability, contact the repository maintainers privately first with:

- A clear description
- Affected version or branch
- Reproduction steps
- Impact assessment
- Suggested fix, if available

Maintainers should acknowledge receipt and coordinate responsible disclosure before public details are posted.
