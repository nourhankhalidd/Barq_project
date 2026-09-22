<img src="assets/barq-logo.svg" alt="BARQ Systems" width="180">

# DevOps Internship Task - Starter v2

**Due date:** ____________________

**Time window:** 4 calendar days from the invitation email date/time.

Read [the task](assessment/TASK.md), then [the API contract](assessment/APPLICATION.md).
Everyone receives this same release. The environment is intentionally broken.
Hidden issue types and count are not disclosed. Investigate this project; do not replace it.

## Included

- Flask API, PostgreSQL, Redis, Docker and NGINX starter files.
- Three historical logs, a question template and documentation templates.
- App-only tests and a recorded challenge script.
- Unimplemented validation, failure-test and backup/restore placeholders.

Use synthetic lab accounts/data only. Supplied values are for this disposable exercise,
never for real services. Keep the lab on your local machine; do not expose it publicly.

## Before you start

- Linux or WSL2, Python 3.12, Git and Docker with Compose.
- Docker Desktop must use Linux containers. Run shell scripts in Linux/WSL.
- Suggested capacity: 2 CPU cores, 4 GB free RAM and 3 GB free disk, plus Docker overhead.
- Internet for first downloads and GitHub. No cloud account or paid registry required.
- Use a machine where container names app-01, app-02, nginx, postgres and redis are unused.
  Do not delete someone else's containers to free those names.
- Intended public port: 8080 before the video, 8090 after the live change.
  If either is occupied, ask the organizer for a documented workstation exception.

## Start

Clone the supplied Git bundle/repository. Keep both release commits and the v2 baseline tag.
Set your own Git name/email before making changes.

From the repository root:

```bash
git status
git log -2 --oneline
cp .env.example .env
docker version
docker compose version
docker compose -p barq-assessment up --build -d
docker compose -p barq-assessment ps -a
docker compose -p barq-assessment logs --no-color
```

The initial environment is not expected to pass. Record what actually happens.
The intended URL is http://127.0.0.1:8080; do not assume the starter configuration is correct.

App-only checks use fake dependencies, not real SQL/Redis or Docker networking:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Your work

- Complete [assessment/TASK.md](assessment/TASK.md).
- Implement validate.py, failure_test.py, backup.sh and restore.sh, or documented equivalents.
  Placeholders deliberately exit 2; they are unfinished deliverables, not validation evidence.
- Create .github/workflows/ci.yml yourself.
- Complete the root report templates and docs/EVIDENCE_INDEX.md.
- Add architecture.png or architecture.pdf.
- Replace this README with copyable setup/build/run/test/failure/backup/restore/cleanup commands.
- Commit as you work. Do not commit real secrets, backups, virtual environments or challenge state.

## Recorded challenge

Use the supplied video_challenge.sh unchanged. Read its code if needed; do not run it early.
After repairing the environment, run it once, for the first time in the video working copy,
during the continuous 12-18 minute recording. The script requires healthy services, both
initial instances and the target network layout. Preflight failures make no runtime changes.

```bash
./video_challenge.sh
```

If you deliberately changed the project name, pass --project YOUR_PROJECT.
An organizer-approved alternate local URL can be passed with --url http://127.0.0.1:PORT.
The script touches only matching Compose-owned lab containers/networks.
Keep the receipt in .assessment/challenge.json for the evidence index. Do not delete the
one-run marker to retry. A local marker is not tamper-proof; ownership is judged from evidence.
Do not use docker compose down to reset the runtime challenge.

## Stop safely

Outside the recorded challenge, docker compose -p barq-assessment down stops this lab.
Do not use --volumes during persistence tests. Avoid global Docker prune/cleanup commands.
Back up anything you need before removing containers; investigate whether data actually persists.


---

# Implemented Solution

##  Scripts

The required assessment scripts were implemented in the repository root:
- `validate.py` — validates public access, endpoints, backend instances, PostgreSQL/Redis readiness, network isolation and prohibited host ports.
- `failure_test.py` — stops one backend, measures availability and errors, restores the backend and verifies recovery.
- `backup.sh` — creates a real PostgreSQL backup using `pg_dump`.
- `restore.sh` — restores PostgreSQL backup data using `pg_restore`.
- `.github/workflows/ci.yml` — runs syntax checks, Docker Compose validation, image build, startup and environment validation.

All scripts use bounded waits, useful PASS/FAIL output and non-zero exit codes on failure.

The scripts target only the assessment Compose project and its named services. They do not target unrelated containers, projects or volumes.

The supplied `video_challenge.sh` and `scripts/video_challenge.py` files were kept unchanged.

## Setup
Create the local environment file:
bash
cp .env.example .env

## Set the local PostgreSQL password in .env :
POSTGRES_PASSWORD=your-local-password
PUBLIC_PORT=8080
### Do not commit .env or real credentials.

## Build and Start
Build the application image: docker compose build
Start the complete stack: docker compose up -d
Check service status: docker compose ps
View service logs: docker compose logs --no-color --tail=200

## Test the Application
The public application is available at: http://127.0.0.1:8080

### Test the required endpoints:
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health
curl -i http://127.0.0.1:8080/ready
curl -i http://127.0.0.1:8080/instance
curl -i http://127.0.0.1:8080/records
curl -i http://127.0.0.1:8080/counter

### Run the complete validation:
python3 validate.py
The validation uses bounded waits and returns a non-zero exit code if any check fails.

## Backend Failure Test

Run: python3 failure_test.py

### The test:
1.Measures baseline availability.
2.Stops app-02.
3.Measures successful and failed requests.
4.Restores app-02.
5.Waits for the backend to become healthy.
6.Verifies that the recovered backend serves requests.

The test records availability and error behavior during the failure window.

## PostgreSQL Backup

Create a PostgreSQL backup: ./backup.sh
List generated backups: ls -lh backups/
The backup uses PostgreSQL's custom dump format.

## PostgreSQL Restore
Restore a backup: ./restore.sh backups/<backup-file>.dump
Verify the restored data: curl -i http://127.0.0.1:8080/records
The restore uses pg_restore and replaces existing database objects in the target database.

## Persistence Test
Create a test record through the API:
curl -i -X POST http://127.0.0.1:8080/records \
  -H 'Content-Type: application/json' \
  -d '{"title":"persistence-verification-record"}'

Recreate the application and PostgreSQL containers without deleting volumes:

docker compose up -d --force-recreate app-01 app-02 postgres

### Check service health:
docker compose ps
### Verify that the record still exists:
curl -i http://127.0.0.1:8080/records

PostgreSQL data is stored in the named postgres-data volume.

## Stop and Cleanup

Stop the stack while preserving persistent volumes: docker compose down
Start the stack again: docker compose up -d
To remove the stack and persistent volumes: docker compose down -v

Warning: docker compose down -v deletes PostgreSQL and Redis persistent data. Create any required backup before using it.

## CI

GitHub Actions runs on both push and pull request events.

The workflow performs:
Repository checkout
Python syntax checks
Docker Compose configuration validation
Application image build
Stack startup
Environment validation
Container status and log collection
Cleanup

### Successful CI run:
https://github.com/nourhankhalidd/Barq_project/actions/runs/35648331157

The validation output included:

PASS: all validation checks passed

A green CI run confirms that the implemented validation passed in the CI environment. It does not guarantee production readiness or availability under every possible failure scenario.

## Container Image Security — Trivy

For container image security, Trivy can be used to scan Docker images for known vulnerabilities and other security issues.
### Example command:
trivy image barq-assessment-app-01:latest
- For a CI/CD pipeline, the scan can also be configured to fail the pipeline when vulnerabilities above a defined severity threshold are detected.

Note: Trivy was considered as part of the security review and CI/CD improvement plan, but no Trivy scan was executed as part of this assessment. Therefore, no vulnerability scan results are claimed here.

## Assessment Questions
1. What failed first? What proved the cause? Which failed attempt taught something?

- The historical logs show the first major failure at approximately 11:05 UTC, when NGINX recorded connection refusals while connecting to the 172.23.0.12:8080 upstream. These requests resulted in HTTP 502 responses.
- The logs prove the connection failure at the NGINX-to-upstream boundary, but the historical logs alone do not prove why that backend stopped accepting connections. Live container inspection would be required to establish the underlying process or container cause.
- For the historical incident, the strongest evidence is the correlation between:
NGINX connect() failed (111: Connection refused) errors
The affected upstream address
Matching request IDs
HTTP 502 responses
Missing corresponding application request records for failed connections
For dependency failures, application logs provide additional evidence such as TimeoutError and InvalidPassword events.
- The initial failure-test implementation could wait indefinitely when an upstream became unavailable. This showed that availability tests must use bounded request timeouts and bounded recovery waits. The test was subsequently changed to use bounded timeouts and explicit recovery checks.

2. What patterns did the logs reveal? How was double-counting avoided?
- The historical logs showed several distinct incident windows:
11:05–11:09: upstream connection refusals affecting app-02
11:12–11:15: Redis dependency timeouts
11:20–11:21: PostgreSQL authentication failures
11:20–11:26: upstream timeout responses
The access log contained 725 valid records, including 95 HTTP 5xx responses.
The application log contained 729 valid records, including HTTP request events and dependency errors.

- Requests were correlated using request_id and timestamps across access, application and error logs.
Exact duplicate access records were identified separately from retries. Five exact duplicate access records were found, but a check for the same request ID appearing with different request records did not identify evidence of application-level retries.
- Application request IDs were also deduplicated before comparing event counts.

3. How do requests flow? Why these ports, networks and readiness checks?

- The request flow is:

Client
  |
  | HTTP :8080
  v
NGINX
  |
  | frontend network
  v
app-01 / app-02 :8080
  |
  | backend network
  +------> PostgreSQL :5432
  |
  +------> Redis :6379
Only NGINX publishes a host port.
The application containers expose port 8080 internally. PostgreSQL and Redis have no host port mappings.

- Port 8080 is the public application port required by the assessment.
The Flask applications listen on internal port 8080.
PostgreSQL uses its standard internal port 5432 and Redis uses its standard internal port 6379.

- NGINX is connected only to the frontend network.
The application containers are connected to both frontend and backend networks.
PostgreSQL and Redis are connected only to the backend network.
This prevents NGINX from directly accessing the database and cache while allowing the application instances to access both dependencies.

- Liveness and readiness have different purposes.
/health checks whether the application process is alive.
/ready checks whether PostgreSQL and Redis dependencies are available.
Docker health checks and the validation script therefore test both application availability and dependency readiness.

4. Why these timeouts, retries, restart settings and resource limits?
- NGINX uses short connection and read timeouts to prevent requests from remaining blocked indefinitely.
The validation and failure tests also use bounded request and recovery waits so a failed dependency cannot cause the assessment itself to hang indefinitely.

- The Compose health checks use a limited number of retries so startup failures are detected within a bounded period.
The NGINX configuration uses proxy_next_upstream off. This makes the behavior during a single-backend failure observable rather than hiding the failure through transparent request retrying.
The failure test therefore measures the actual availability impact when one backend is stopped.

- Application, PostgreSQL and Redis services use restart: unless-stopped where appropriate for automatic recovery from unexpected container termination while still allowing deliberate operator shutdown.

- Application containers have bounded CPU and memory resources to prevent one application instance from consuming unlimited host resources.
The configured limits are assessment-sized rather than production capacity recommendations.

5. When should validation fail? What does green CI prove, or not prove?
- Validation should fail when a required service is unavailable, an endpoint does not behave as expected, dependencies are not ready, prohibited ports are exposed, or required network isolation is violated.
The script returns a non-zero exit status whenever a validation check fails, allowing CI to detect the failure.

- A green CI run proves that the automated checks passed in the GitHub Actions environment for that commit.
It does not prove production readiness, eliminate all vulnerabilities, prove every possible failure mode, or guarantee long-term availability.

6. Which single points of failure remain? How would you fix them in production?
- The current assessment architecture still has several potential single points of failure:
A single NGINX container
A single PostgreSQL instance
A single Redis instance
A single Docker host

- In production, these could be addressed using redundant load balancers, highly available PostgreSQL, replicated cache infrastructure where appropriate, multiple hosts or availability zones, and centralized monitoring.

7. What would you improve?
- Potential production improvements include:
Highly available PostgreSQL with tested failover
Redis replication or a managed highly available cache
Multiple NGINX/load-balancer instances
Centralized metrics, logs and alerting
Automated vulnerability remediation and image scanning
Secret management through a dedicated secret-management system
Regular encrypted backups with off-host storage
Restore drills and recovery-time objectives
TLS termination and stronger ingress controls
More comprehensive distributed tracing and request correlation
These are production plans and are separate from the fixes implemented for this assessment.

8. How was AI-assisted work verified?

AI assistance was used for troubleshooting, documentation structure and review Scripts.
NOTE: AI-generated suggestions were not treated as proof of correctness. Commands were executed locally, Docker Compose behavior was verified, endpoints were tested, failure and recovery scenarios were executed, PostgreSQL backup and restore were demonstrated, and the GitHub Actions workflow was run successfully.