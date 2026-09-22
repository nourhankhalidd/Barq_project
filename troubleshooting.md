# Troubleshooting Journal

This journal records the main troubleshooting investigations performed during the BARQ Academy assessment. Entries are based on the actual repository history, observed behavior, commands/tests, and subsequent retesting.

## Entry 1 — Application healthcheck endpoint
### Symptom
`app-01` and `app-02` remained unhealthy even though the application itself was running.
### Hypothesis
The Docker healthcheck might be testing an endpoint that does not exist in the application.
### Command or test
The application routes were inspected with:
```bash
grep -n '@app\.' app/server.py
```
The Docker Compose healthcheck configuration was also reviewed.
### Actual output
The application exposed `/health`, while the Compose healthcheck was requesting `/healthz`. Logs showed repeated `404 GET /healthz` requests.
### Failed attempt and what changed your thinking
The initial healthcheck configuration assumed `/healthz` existed. The repeated 404 responses showed that the problem was the healthcheck URL rather than application availability.
### Root cause
The healthcheck URL in the Compose configuration was incorrect.
### Fix
Changed the healthcheck endpoint from `/healthz` to `/health`.
### Retest evidence
`docker compose ps` showed both application containers as `healthy`.
### Related commit
`06508dc` — `fix: correct healthcheck endpoint from /healthz to /health`
### Remaining uncertainty
The healthcheck verifies the application's health endpoint but does not by itself prove that all application dependencies are healthy.

## Entry 2 — Application binding address
### Symptom
NGINX could not reliably reach the application containers even after the healthcheck endpoint was corrected.
### Hypothesis
The Flask application might be listening only on the container loopback interface.
### Command or test
The application configuration in `docker-compose.yml` was inspected, and the application was tested from inside the container.
### Actual output
`APP_HOST` was configured as `127.0.0.1`.
### Failed attempt and what changed your thinking
Testing the application locally inside the container worked, but communication from another container such as NGINX failed. This indicated that loopback binding was preventing inter-container access.
### Root cause
The application was bound to `127.0.0.1`, which accepts connections only from the same container.
### Fix
Changed `APP_HOST` to `0.0.0.0` so the application listens on the container network interface.
### Retest evidence
The application responded successfully from inside the container, and the configuration allowed other containers to reach the application listener.
### Related commit
`3af347e` — `fix: bind app to 0.0.0.0 instead of 127.0.0.1`
### Remaining uncertainty
The remaining external connection issue was investigated separately as an NGINX port/upstream configuration problem.

## Entry 3 — NGINX published port
### Symptom
The NGINX service was reachable using the expected external port configuration, but the published host port did not match the port expected by the NGINX container listener.
### Hypothesis
The host-to-container port mapping was incorrect.
### Command or test
The Docker Compose port mapping and NGINX listener configuration were compared.
### Actual output
The published port did not align with the container port on which NGINX was listening.
### Failed attempt and what changed your thinking
Changing the application binding did not resolve the external access problem. Comparing the host mapping with the NGINX listener showed that the problem was at the Docker port publishing layer.
### Root cause
The NGINX published port was misconfigured.
### Fix
Aligned the published NGINX port with the container listener.
### Retest evidence
The NGINX service became reachable through the configured public port.
### Related commit
`df4f409` — `fix: align nginx published port with container listener`
### Remaining uncertainty
The public port remains a deployment configuration value and should be kept consistent with the environment-specific `.env` configuration.


## Entry 4 — NGINX app-01 upstream port
### Symptom
NGINX still could not successfully proxy requests to `app-01` after the application binding and published-port issues were corrected.
### Hypothesis
The NGINX upstream configuration might be pointing to the wrong internal application port.
### Command or test
The NGINX upstream configuration in `docker-compose.yml` and the application listening port were compared.
### Actual output
The `app-01` upstream used an incorrect port.
### Failed attempt and what changed your thinking
The application was reachable on its configured internal port, but NGINX was attempting to connect to a different port. This isolated the problem to the upstream definition.
### Root cause
The `app-01` NGINX upstream port was incorrect.
### Fix
Changed the `app-01` upstream to the application's actual internal listener port.
### Retest evidence
Requests through NGINX could reach `app-01` after the upstream correction.
### Related commit
`e0d9cee` — `fix: correct nginx app-01 upstream port`
### Remaining uncertainty
The same upstream configuration needed to be checked for consistency across both application replicas.

## Entry 5 — Unique instance identity
### Symptom
Both application containers could respond, but their instance identity was not unique.
### Hypothesis
The second application container might be using the same instance ID as the first container.
### Command or test
The Compose environment configuration for `app-01` and `app-02` was inspected and the `/instance` endpoint was used to identify the backend handling a request.
### Actual output
`app-02` was configured with the wrong instance identity.
### Failed attempt and what changed your thinking
The load-balancing setup appeared to work, but identical instance identifiers made it difficult to verify which backend was serving a request.
### Root cause
`app-02` had not been assigned a unique instance ID.
### Fix
Assigned a distinct instance ID to `app-02`.
### Retest evidence
The `/instance` endpoint returned different identities for the two application replicas, allowing load balancing to be observed.
### Related commit
`a7f57cd` — `fix: assign unique instance id to app-02`
### Remaining uncertainty
Instance identity is useful for observability and testing but does not itself provide availability guarantees.

## Entry 6 — Internal dependency ports
### Symptom
Application dependency checks were failing even though the dependency containers were running.
### Hypothesis
The application might be trying to reach PostgreSQL or Redis using externally published ports instead of Docker-internal service ports.
### Command or test
The dependency URLs and Docker Compose service/network configuration were compared.
### Actual output
The application dependency configuration did not consistently use the internal container ports.
### Failed attempt and what changed your thinking
The services were available within the Compose network, but application-to-dependency communication still failed. This indicated that host-published ports were being confused with internal service ports.
### Root cause
Internal dependency connections were configured with incorrect ports.
### Fix
Corrected the dependency ports to use the service ports available on the backend Docker network.
### Retest evidence
PostgreSQL and Redis dependency checks became reachable from the application containers.
### Related commit
`f7bdf25` — `fix: correct internal dependency ports`
### Remaining uncertainty
This configuration assumes all application and dependency services continue to use the documented internal ports.

## Entry 7 — PostgreSQL authentication credentials
### Symptom
The application reported PostgreSQL authentication failures.
### Hypothesis
The PostgreSQL credentials configured for the application did not match the credentials configured for the PostgreSQL service.
### Command or test
The PostgreSQL connection configuration and Compose environment variables were compared.
### Actual output
The application and PostgreSQL service were using inconsistent authentication credentials.
### Failed attempt and what changed your thinking
The PostgreSQL container was running and reachable, so the problem was not container availability. The authentication error narrowed the problem to credentials.
### Root cause
PostgreSQL authentication credentials were misaligned between the application and database service.
### Fix
Aligned the PostgreSQL credentials used by the application and PostgreSQL service.
### Retest evidence
PostgreSQL readiness and application database operations succeeded after the credentials were corrected.
### Related commit
`3489090` — `fix: correct PostgreSQL authentication credentials`
### Remaining uncertainty
Credentials stored in local environment files must still be protected and rotated appropriately in a production deployment.

## Entry 8 — Application containers running as non-root
### Symptom
The application container configuration required a more secure runtime identity.
### Hypothesis
The application should not run as the default root user.
### Command or test
The Dockerfile and container runtime configuration were inspected.
### Actual output
The application image configuration was updated to use a dedicated non-root user.
### Failed attempt and what changed your thinking
Running the application with elevated container privileges increases the impact of a potential container compromise. This was treated as a container-hardening issue rather than a functional failure.
### Root cause
The initial application runtime used the default container user.
### Fix
Configured the Docker image to run the application as a dedicated non-root user.
### Retest evidence
The application continued to build and run successfully after the user change.
### Related commit
`ad267ea` — `fix: run application containers as non-root user`
### Remaining uncertainty
Running as non-root reduces privilege but does not eliminate vulnerabilities inside the image or application.

## Entry 9 — PostgreSQL persistent storage
### Symptom
Database data needed to survive application/database container recreation.
### Hypothesis
A named Docker volume should be used for PostgreSQL data rather than relying on the container filesystem.
### Command or test
The Compose volume configuration was reviewed and PostgreSQL persistence was tested by recreating the database container.
### Actual output
PostgreSQL was configured with the named volume:
`barq-assessment_postgres-data`
### Failed attempt and what changed your thinking
No failed persistence attempt was recorded. The test was designed to verify that the database data was not tied to the lifetime of the container.
### Root cause
Not applicable; this was a persistence design and verification task.
### Fix
Configured PostgreSQL to use a named Docker volume.
### Retest evidence
A test record remained available after:
```bash
docker compose up -d --force-recreate postgres
```
### Related commit
`a66b7b1` — `fix: persist PostgreSQL data on named volume`
### Remaining uncertainty
A Docker named volume protects against container recreation but is not a substitute for external backups or disaster recovery.

## Entry 10 — Remove unnecessary PostgreSQL and Redis published ports
### Symptom
PostgreSQL and Redis did not need to be directly reachable from the host.
### Hypothesis
Removing host port publishing would reduce unnecessary external exposure while preserving internal application connectivity.
### Command or test
The Compose `ports` configuration and service connectivity were reviewed.
### Actual output
PostgreSQL and Redis were accessible through the backend Docker network without needing host-published ports.
### Failed attempt and what changed your thinking
The application only required internal service-to-service connectivity. Publishing the database and Redis ports was unnecessary for the required architecture.
### Root cause
Database and Redis ports were unnecessarily exposed to the host.
### Fix
Removed the published PostgreSQL and Redis ports.
### Retest evidence
The application continued to connect to PostgreSQL and Redis through the backend network.
### Related commit
`b3ec7b2` — `fix: remove published PostgreSQL and Redis ports`
### Remaining uncertainty
Network isolation should still be verified whenever Compose networking is changed.

## Entry 11 — NGINX network isolation
### Symptom
The architecture required NGINX to be the public entry point while PostgreSQL and Redis remained internal services.
### Hypothesis
NGINX should not be connected to the backend network containing PostgreSQL and Redis.
### Command or test
Docker Compose network membership and direct connectivity were inspected.
### Actual output
The NGINX service was isolated from the backend network.
### Failed attempt and what changed your thinking
The initial architecture exposed more connectivity than necessary. Separating frontend and backend networks reduced the paths available to reach internal services.
### Root cause
Network boundaries needed to explicitly enforce the intended request flow.
### Fix
Configured NGINX on the frontend network and application services on both frontend and backend networks, while PostgreSQL and Redis remained backend-only.
### Retest evidence
Direct access from NGINX to PostgreSQL and Redis was not available through network isolation, while NGINX could still reach the application containers.
### Related commit
`2b49760` — `fix: isolate nginx from backend network`
### Remaining uncertainty
Docker network isolation protects this Compose deployment model; production environments should enforce equivalent segmentation at the infrastructure level.

## Entry 12 — Automatic application restart policy
### Symptom
The application services needed to recover automatically from container-level failures.
### Hypothesis
A restart policy would allow failed application containers to be restarted by Docker.
### Command or test
The Compose restart configuration was reviewed and container behavior was tested as part of the service availability checks.
### Actual output
An automatic restart policy was added to the application services.
### Failed attempt and what changed your thinking
A container that exits unexpectedly should not require manual intervention for every restart. This was treated as an availability improvement rather than a replacement for application-level recovery.
### Root cause
The initial service definition did not explicitly provide automatic restart behavior.
### Fix
Configured an automatic restart policy for the application containers.
### Retest evidence
The Compose configuration included the restart policy and the stack remained recoverable through container restart behavior.
### Related commit
`8e768ee` — `fix: configure automatic app restart policy`
### Remaining uncertainty
Restart policies cannot fix persistent application or dependency failures and can potentially create restart loops.

## Entry 13 — Application resource limits
### Symptom
The application containers needed bounded resource usage.
### Hypothesis
Docker Compose resource limits could reduce the risk of a single application container consuming uncontrolled resources.
### Command or test
The Compose service definitions were reviewed and resource limits were added.
### Actual output
Resource limits were configured for the application services.
### Failed attempt and what changed your thinking
Availability is not only about restarting failed containers. Resource exhaustion can also affect the host and other services, so resource boundaries were added as a defensive control.
### Root cause
The initial Compose configuration did not define explicit application resource limits.
### Fix
Added CPU/memory resource limits to the application containers.
### Retest evidence
The updated Compose configuration loaded successfully and the application stack remained operational under the configured limits.
### Related commit
`d286daa` — `fix: add application resource limits`
### Remaining uncertainty
The configured limits were chosen for the assessment environment and should be tuned using production workload measurements.

## Entry 14 — Secret-bearing configuration tracking
### Symptom
`config/app.env` contained database and Redis connection credentials and was tracked by Git.
### Hypothesis
The configuration file should be removed from Git tracking and replaced by a local environment mechanism.
### Command or test
Git tracking and repository configuration were inspected.
### Actual output
`config/app.env` contained sensitive connection information and had existed in repository history.
### Failed attempt and what changed your thinking
Keeping the file tracked would allow anyone with repository access to retrieve the credentials. Removing it from current tracking reduced future exposure but did not erase historical commits.
### Root cause
A secret-bearing environment file had been committed to the repository.
### Fix
Removed `config/app.env` from current Git tracking and ensured the environment file was ignored.
### Retest evidence
The application continued to run using local environment configuration without requiring the secret file to be committed.
### Related commit
`d526801` — `security: stop tracking config/app.env in git`
### Remaining uncertainty
The secret remains in previous Git history. In a real environment, the affected credentials should be revoked/rotated. History rewriting was not performed because it would alter shared repository history.

## Entry 15 — Secrets in image and Compose configuration
### Symptom
Sensitive values needed to be prevented from appearing in the built image or hardcoded Compose configuration.
### Hypothesis
Secrets should be supplied through environment configuration rather than embedded in the Docker image or Compose source.
### Command or test
The Dockerfile and Compose configuration were reviewed after the secret-tracking issue was identified.
### Actual output
Sensitive configuration was removed from the image/Compose setup.
### Failed attempt and what changed your thinking
Removing the environment file from Git was not sufficient if credentials could still be embedded elsewhere in the Docker build or Compose configuration.
### Root cause
Secret values had to be removed from all current build/runtime configuration locations, not only from Git tracking.
### Fix
Removed secrets from the image and Compose configuration and used environment variables for runtime configuration.
### Retest evidence
The application image was checked to ensure the removed environment file was not present.
### Related commit
`90edae1` — `security: remove secrets from image and compose`
### Remaining uncertainty
Production deployments should use a dedicated secret-management system rather than local `.env` files.