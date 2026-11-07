# Preparing deployment

The `Deploy backend` and `Deploy frontend` GitHub Actions workflows are manual. Each runs its
checks before connecting to the server, only deploys `main`, and uses the GitHub `production`
environment. They are not active until committed and pushed.

## Server prerequisites

- Docker with the Compose plugin, and curl.
- An SSH deployment account that can write `/opt/cp-hub` and run Docker Compose. Docker access
  grants substantial privileges; restrict the account and its key accordingly.
- `/etc/cp-hub/backend.env`, readable by the deployment account, with production settings. Keep
  this file outside both repositories, limit its permissions, and back it up securely.
- An HTTPS reverse proxy. Serve `/opt/cp-hub/frontend/current` as an SPA, forwarding `/api/v1/`
  unchanged to `http://127.0.0.1:8000`. Configure an SPA fallback to `index.html`. Configure TLS
  after DNS is pointed; don't use production credentials over plain HTTP.

The backend environment must set `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` and
`DATABASE_URL`, using `db` as the database host inside Compose. It must also set `DEBUG=false`,
`AUTH_JWT_SECRET` to a strong unique secret, `AUTH_REFRESH_COOKIE_SECURE=true`,
`FRONTEND_BASE_URL` to the HTTPS frontend URL, and any required email and CORS settings. The
credentials in `DATABASE_URL` must match the PostgreSQL values and be URL-encoded if needed.
PostgreSQL image initialization variables apply only to a new volume; changing them later does
not change the existing database credentials.

Notify-Hub settings may remain unset during initial setup. Do not start notification worker or
reminder schedules until Notify-Hub is configured and the pending-event policy is decided. Resend
configuration is needed for password emails. Neither service is provisioned by these workflows.

Create and test a backup and restoration process before storing real data. The deployment runs
Alembic migrations before restarting the API. A failed release does not automatically reverse
database migrations; recovery must consider database compatibility and backups. Configure the
first administrator separately before expecting anyone to sign in.

## GitHub setup

In **each** repository, create a `production` environment and add environment secrets:

- `VPS_HOST`: VPS hostname or IP address.
- `VPS_USER`: the deployment SSH username.
- `VPS_SSH_PRIVATE_KEY`: a dedicated deployment private key, not a personal administrator key.
- `VPS_SSH_KNOWN_HOSTS`: the verified SSH host-key entry for the VPS, including its hostname/IP.

Provision the matching public key on the server and verify the host fingerprint independently.
Do not paste private keys into chat. Protect the production environment as appropriate for your
GitHub plan. Both workflows require the same-origin proxy layout described above.

Once the VPS and secrets are ready, run **Actions → Deploy backend → Run workflow** on `main`,
then **Actions → Deploy frontend → Run workflow**. Check the run results, HTTPS access, login,
permissions, migrations and a real backup restore before inviting users.

The backend workflow uses a persistent named Compose database volume; release directories alone
are not database backups. Frontend releases are activated through the `current` symlink. Old
release directories are not automatically removed.
