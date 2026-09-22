# Security and production-readiness review

## Finding 1: PostgreSQL password hardcoded in docker-compose.yml
- Risk and evidence: `POSTGRES_PASSWORD: BarqLabOnly_7qN2vK8c` was
  written directly in the tracked docker-compose.yml file.
- Impact: Anyone with read access to the repository (or its git
  history) could authenticate to PostgreSQL.
- Implemented fix / commit: replaced with `${POSTGRES_PASSWORD}`
  variable substitution from a local, gitignored `.env` file; added
  `.env.example` with a placeholder. (insert commit hash)
- Production follow-up: use a secret manager instead of a local .env
  file for production deployments.
- How to verify: `grep POSTGRES_PASSWORD docker-compose.yml` shows only
  the variable reference, never a literal password.

## Finding 2: config/app.env tracked in git with real credentials
- Risk and evidence: `config/app.env` (containing DATABASE_URL and
  REDIS_URL with the real password) was tracked since the baseline
  commit and appeared in `git ls-files`.
- Impact: Same credential exposure as Finding 1, plus the file was also
  being copied into the built Docker image layer.
- Implemented fix / commit: `git rm --cached config/app.env`; file
  remains on disk (required by `env_file:`) but is no longer tracked;
  added to `.gitignore`. (insert commit hash)
- Production follow-up: none additional beyond secret-manager adoption.
- How to verify: `git ls-files | grep app.env` returns nothing.
- Limitation: the original password remains visible in the repository's
  prior git history (baseline commit). Rewriting history was avoided to
  prevent disrupting the shared/graded repository; documented here as an
  accepted, disclosed limitation rather than a hidden gap.

## Finding 3: Secret copied into the Docker image layer
- Risk and evidence: Dockerfile contained
  `COPY config/app.env /srv/app.env`, embedding the secret file inside
  an image layer retrievable via `docker history` or by anyone who pulls
  the image.
- Impact: Secret exposure independent of git access — anyone with the
  built image could extract the credentials.
- Implemented fix / commit: removed the COPY line entirely; the app now
  receives DATABASE_URL/REDIS_URL only via `env_file:` at container
  runtime, never baked into the image. (insert commit hash)
- Production follow-up: none; this is the correct pattern.
- How to verify: `docker history barq-assessment-app-01` shows no layer
  copying app.env; `docker run --rm barq-assessment-app-01 cat
  /srv/app.env` fails (file does not exist in the image).

## Finding 4: Containers ran as root
- Risk and evidence: Dockerfile created a non-root `app` user but then
  set `USER root` before CMD, so the process ran as root inside the
  container.
- Impact: A container escape or code-execution vulnerability in the app
  would grant root privileges inside the container (and a larger attack
  surface generally), violating least-privilege practice.
- Implemented fix / commit: removed the `USER root` override so the
  container runs as the unprivileged `app` (uid 10001) user.
  (insert commit hash)
- Production follow-up: consider read-only root filesystem
  (`read_only: true`) and dropped Linux capabilities for further
  hardening.
- How to verify: `docker compose exec app-01 whoami` returns `app`, not
  `root`.

## Finding 5: PostgreSQL and Redis ports published to the host
- Risk and evidence: postgres exposed `127.0.0.1:15432:5432` and redis
  exposed `127.0.0.1:16379:6379`, contradicting the brief's explicit
  "do not publish" requirement.
- Impact: Any local process (or, if the host firewall is misconfigured,
  any network peer) could connect directly to the databases, bypassing
  application-level access control entirely.
- Implemented fix / commit: removed both `ports:` entries; databases are
  reachable only from other containers on the internal `backend`
  network. (insert commit hash)
- Production follow-up: none additional; this matches production
  practice. For remote administration, use `docker compose exec` or a
  bastion host instead of published ports.
- How to verify: `docker compose ps` shows no host port mapping for
  postgres/redis; `validate.py`'s host port checks pass.

## Finding 6: NGINX had direct network access to PostgreSQL and Redis
- Risk and evidence: NGINX was connected to both `frontend` and
  `backend` networks, though it only proxies to app-01/app-02.
- Impact: A compromised or misconfigured NGINX (the internet-facing
  component) could reach the databases directly, bypassing the
  application entirely.
- Implemented fix / commit: removed NGINX from the `backend` network;
  it is now connected only to `frontend`. (insert commit hash)
- Production follow-up: consider a dedicated network policy/service
  mesh for defense in depth beyond Compose network segmentation.
- How to verify: `docker compose exec nginx nc -zv -w2 postgres 5432`
  fails/times out; `validate.py`'s network isolation checks pass.

## Finding 7: No resource limits on application containers
- Risk and evidence: The starter defined no CPU/memory limits for
  app-01/app-02, so a runaway process or memory leak could exhaust host
  resources and affect other containers.
- Impact: Availability risk — one misbehaving container could degrade
  or crash the whole host.
- Implemented fix / commit: added
  `deploy.resources.limits: {cpus: "0.50", memory: 256M}` to the shared
  `x-app` anchor, applying to app-01 and app-02. (insert commit hash)
- Production follow-up: also set limits for nginx/postgres/redis, and
  add `reservations` (not just `limits`) for predictable scheduling in
  orchestrated environments (Swarm/Kubernetes); tune values based on
  real load testing rather than assessment defaults.
- How to verify: `docker inspect app-01 --format '{{.HostConfig.Memory}}
  {{.HostConfig.NanoCpus}}'` shows the configured limits.

## Finding 8: No automatic upstream failover in NGINX (max_fails=0)
- Risk and evidence: nginx.conf sets `max_fails=0` for both upstream
  servers, and `proxy_next_upstream off;` — NGINX never marks a backend
  as down and never retries a failed request on the other backend within
  the same client request.
- Impact: During a backend outage, roughly half of in-flight requests
  time out (bounded by `proxy_read_timeout: 3s`) instead of being
  transparently served by the healthy backend, as measured by
  failure_test.py (10/20 requests failed while app-02 was stopped).
- Implemented fix / commit: none — left unchanged as it was not one of
  the required fixes for this assessment; explicitly documented instead
  of silently left broken.
- Production follow-up: configure `max_fails=2-3 fail_timeout=5-10s` and
  enable `proxy_next_upstream error timeout` so failed requests are
  retried on a healthy backend within the same client request.
- How to verify: rerun `failure_test.py` after the change and confirm
  the "errors" count during the failure phase drops toward 0.

## Finding 9: Duplicated secret across two files
- Risk and evidence: POSTGRES_PASSWORD exists in both `.env` (used by
  Compose for variable substitution) and inside `config/app.env`'s
  DATABASE_URL (used by the app for its own connection).
- Impact: No direct exposure risk (both files are gitignored), but
  operational risk — rotating the password requires updating two files
  in sync; missing one causes authentication failures.
- Implemented fix / commit: none; documented as an accepted limitation
  of this assessment's scope.
- Production follow-up: use a single secret source (e.g. a secret
  manager injecting the same value into both consumers, or an
  application config that reads the password once and constructs the
  connection string itself) to eliminate duplication.
- How to verify: N/A (documentation-only finding).

## Finding 10: No centralized logging or monitoring
- Risk and evidence: Container logs are only accessible via
  `docker compose logs`; there is no log aggregation, alerting, or
  metrics collection (e.g. Prometheus, Grafana, ELK/Loki).
- Impact: In production, an outage or attack could go unnoticed until a
  user reports it; historical log analysis (as done manually for
  log_analysis.md) would not scale operationally.
- Implemented fix / commit: none; out of scope for this assessment.
- Production follow-up: ship container logs to a centralized system
  (e.g. Loki/ELK), add health-based alerting, and expose
  application/NGINX metrics for a monitoring dashboard.
- How to verify: N/A (documentation-only finding).

## Finding 11: Backup strategy is manual and untested for disaster recovery beyond a single restore
- Risk and evidence: backup.sh/restore.sh prove a single successful
  restore cycle, but there is no automated backup schedule, retention
  policy, off-host storage, or backup encryption.
- Impact: A single successful manual restore does not guarantee
  recoverability from a real incident (e.g. host loss, corrupted
  backup, or backup taken during a partial failure).
- Implemented fix / commit: backup.sh/restore.sh implemented and
  verified once (insert commit hash).
- Production follow-up: automate scheduled backups, store them off-host
  (e.g. object storage), encrypt backups at rest, and periodically test
  restores (not just once) as part of routine operations.
- How to verify: N/A beyond the single documented restore test.