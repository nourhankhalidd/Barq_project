# Technical decisions

## Decision 1: Bind Flask app to 0.0.0.0 instead of 127.0.0.1
- Choice: Set APP_HOST=0.0.0.0 in docker-compose.yml x-app anchor
- Why: The starter had APP_HOST=127.0.0.1, which only accepts loopback
  traffic inside each container. NGINX runs in a separate container and
  could not reach app-01/app-02 over the Docker network with that setting.
- Alternative: Use host networking mode (rejected — breaks network
  isolation requirements and container-name-based service discovery).
- Trade-off: None meaningful; 0.0.0.0 is required for any multi-container
  proxy setup and does not expose the app beyond the Docker network since
  no app port is published to the host.
- Evidence / commit: 3af347e "fix: bind app to 0.0.0.0 instead of
  127.0.0.1". Verified via `docker compose exec app-01 python -c
  "urlopen('http://127.0.0.1:8080/health')"` returning 200 before the
  external NGINX path was even fixed, isolating this change from the
  NGINX port issue.
- Production improvement: none needed; this is already the correct
  production pattern.

## Decision 2: Named PostgreSQL volume mounted at the real PGDATA path
- Choice: Mount `postgres-data:/var/lib/postgresql/data` and remove the
  conflicting `tmpfs: [/var/lib/postgresql/data]` entry.
- Why: The starter defined a named volume at
  `/var/lib/postgresql/backup` (not PostgreSQL's actual data directory)
  while simultaneously mounting a `tmpfs` at the real data path
  `/var/lib/postgresql/data`. tmpfs is RAM-backed and is wiped whenever
  the container is removed, so every record disappeared on
  `docker compose down` + `up`, despite the named volume appearing to
  exist.
- Alternative: Keep tmpfs for faster test runs and rely on backup/restore
  only (rejected — contradicts the assessment's persistence requirement
  and the "record survives recreation" proof).
- Trade-off: Slightly slower disk I/O than tmpfs, acceptable for this
  workload.
- Evidence / commit: a66b7b1 "fix: persist PostgreSQL data on named
  volume". Verified by creating a record, running
  `docker compose up -d --force-recreate app-01 app-02 postgres`, and
  confirming the record was still present in GET /records afterward.
- Production improvement: add automated volume backups (see
  security_review.md) and consider a managed PostgreSQL service instead
  of a self-hosted volume for production durability guarantees.

## Decision 3: Removed published host ports for PostgreSQL and Redis
- Choice: Deleted `ports: ["127.0.0.1:15432:5432"]` and
  `ports: ["127.0.0.1:16379:6379"]` from postgres and redis services.
- Why: The brief explicitly requires "Do not publish app, PostgreSQL or
  Redis ports." Publishing them let any process on the host connect
  directly to the databases, bypassing the app and NGINX entirely.
- Alternative: Keep the ports but restrict via firewall rules (rejected —
  unnecessary complexity when Compose's own port publishing can simply
  be omitted; the databases only need to be reachable from other
  containers on the `backend` network).
- Trade-off: Debugging PostgreSQL/Redis directly from the host now
  requires `docker compose exec` instead of a local client on
  15432/16379.
- Evidence / commit: b3ec7b2 "fix: remove published PostgreSQL and Redis
  ports". Verified with `docker compose ps` showing no host port mapping
  and `validate.py`'s "Host port restrictions" section passing.
- Production improvement: none; this matches production best practice.

## Decision 4: Isolated NGINX from the backend network
- Choice: Changed NGINX's `networks:` from `[frontend, backend]` to
  `[frontend]` only.
- Why: The brief requires blocking direct NGINX access to
  PostgreSQL/Redis. NGINX only needs to reach app-01/app-02, which are
  also on `frontend`, so backend access was unnecessary and a security
  risk (NGINX is the internet-facing container and a compromise there
  should not give direct database access).
- Alternative: Keep NGINX on both networks and rely on application-layer
  controls only (rejected — network-layer isolation is a stronger,
  brief-mandated control and is nearly free to implement).
- Trade-off: None; app-01/app-02 remain on both networks so they can
  still reach PostgreSQL/Redis on `backend`.
- Evidence / commit: 2b49760 "fix: isolate nginx from backend network".
  Verified in `validate.py`'s "Network isolation" section (PASS: NGINX
  is isolated from backend network).
- Production improvement: none for this scope; a production setup might
  add a dedicated network policy / service mesh for finer-grained rules.

## Decision 5: PostgreSQL password sourced from a gitignored .env file
- Choice: Replaced the hardcoded `POSTGRES_PASSWORD` literal in
  docker-compose.yml with `${POSTGRES_PASSWORD}`, sourced from a local
  `.env` file; added `.env.example` with a placeholder value; removed
  `config/app.env` from git tracking (it also contains the same
  password inside DATABASE_URL) and stopped copying it into the Docker
  image.
- Why: The brief requires keeping secrets out of images, code and
  Compose, and ignoring secret files while providing a safe example.
  The password was previously visible to anyone with read access to the
  repository and was also baked into the image via
  `COPY config/app.env /srv/app.env`.
- Alternative: Use Docker secrets / an external secret manager (rejected
  for this assessment scope — adds infrastructure not required by the
  brief; documented as a production follow-up instead).
- Trade-off: The same password now exists in two separate files (.env
  for Compose variable substitution, config/app.env for the app's
  DATABASE_URL/REDIS_URL via env_file), which must be kept manually in
  sync. This duplication is itself flagged as a risk in
  security_review.md.
- Evidence / commit: (git rm --cached config/app.env commit) and
  (docker-compose.yml ${POSTGRES_PASSWORD} commit — insert your actual
  hashes). Verified with `docker compose down -v && docker compose up -d
  --build` followed by `docker compose ps` showing postgres healthy,
  proving the substituted password matched.
- Production improvement: adopt a secret manager (e.g. Docker
  Swarm/Kubernetes secrets, HashiCorp Vault, or the cloud provider's
  secret store) to eliminate password duplication and enable rotation
  without editing multiple files.