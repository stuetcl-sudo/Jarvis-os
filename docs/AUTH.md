# Local authentication

Jarvis-os uses local SQLite-backed users and opaque server-side sessions. No default account is created and there is no web bootstrap endpoint.

## Role matrix

| Role | Public family dashboard | Mission Control | Technical write APIs |
| --- | --- | --- | --- |
| `owner` | Yes | Yes | Yes, with a valid session and CSRF token |
| `adult` | Yes | No | No |
| `child` | Yes | No | No |
| `wall_display` | Yes | No | No |
| Anonymous | Yes | Redirected to login | No |

The family dashboard at `/` remains publicly readable by design in v0.8. Existing read-only technical GET APIs are unchanged in this task.

## Create and manage users

Run the CLI inside the application container. Passwords are requested interactively with `getpass`; they must never be supplied as command-line arguments.

```bash
docker compose exec jarvis-os \
  python -m app.auth.cli create-user \
  --username owner \
  --display-name "Owner" \
  --role owner
```

Available commands:

```text
create-user --username NAME --display-name NAME --role ROLE
list-users
disable-user --username NAME
enable-user --username NAME
reset-password --username NAME
```

`list-users` never prints password hashes. Disabling a user immediately removes all of that user's active sessions. Resetting a password also removes existing sessions.

## Password storage

Passwords must contain 12–128 characters. Jarvis-os uses `pwdlib[argon2]` with `PasswordHash.recommended()` and stores only Argon2 password hashes. Unknown usernames are checked against a dummy Argon2 hash so the normal failure path is less timing-revealing. Unknown usernames and incorrect passwords receive the same generic response.

## Login throttling

Failed login attempts are persisted in SQLite. The rate-limit key is a SHA-256 digest derived from the normalized username and request client address; the raw address is not stored in the login-attempt table. Defaults are five failures in fifteen minutes. Successful login clears the matching failure record.

## Sessions and cookies

A successful login creates a new opaque random token and invalidates the user's previous sessions. Only SHA-256 of the token is stored in `auth_sessions`; the raw token exists only in the `jarvis_session` browser cookie.

Cookie properties:

- `HttpOnly=true`
- `SameSite=Strict`
- `Path=/`
- `Secure` follows `AUTH_COOKIE_SECURE`

Normal sessions expire after `AUTH_SESSION_HOURS`. Wall-display sessions use `AUTH_WALL_SESSION_DAYS`. Expired sessions and sessions belonging to disabled users fail closed. Logout removes the database session and expires the cookie.

`AUTH_COOKIE_SECURE=false` is only appropriate for the current local HTTP setup. Every HTTPS deployment must set:

```text
AUTH_COOKIE_SECURE=true
```

## CSRF protection

Each session has a separate random CSRF token. It is returned only by `GET /api/auth/me` to the authenticated browser. Mission Control keeps it only in JavaScript memory and sends it in `X-CSRF-Token` on every state-changing request. The server compares it using a timing-safe comparison.

SameSite cookies are an additional protection, not a replacement for CSRF validation. Logout also requires the current CSRF token.

## Login and logout flow

- `GET /login` serves the Danish login page.
- `POST /api/auth/login` validates credentials, rate limits failures and sets `jarvis_session`.
- `GET /api/auth/me` returns safe user fields and the current CSRF token.
- `POST /api/auth/logout` requires the session CSRF token, deletes the server-side session and expires the cookie.
- Anonymous requests to `/admin` redirect only to the local `/login?next=/admin` path.

No passwords, password hashes, raw session tokens, CSRF tokens or full cookie headers are written to authentication audit logs.
