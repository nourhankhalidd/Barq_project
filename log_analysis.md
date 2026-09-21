# Log analysis

## Scope and method

These logs contain synthetic historical lab data. The original files under `logs/` were not modified.

* `access.log`: NGINX client-facing requests in JSON Lines format.
* `error.log`: NGINX diagnostic text.
* `application.log`: structured application requests/events in JSON Lines format.
* All timestamps were interpreted as UTC.
* Correlation used `request_id`, timestamps, upstream address, and application `instance_id`.
* `request_time` is measured in seconds and was converted to milliseconds for latency reporting.
* A log record is not always a distinct client request.
* Exact duplicate records were separated from legitimate multiple events sharing a request ID.
* Access-log retries were only counted when the same request ID had multiple **non-identical** access records.
* The supplied logs are historical incident evidence and do not represent the complete state of the current environment.

The analysis was performed using `analyze_logs.py`. The generated output was saved to `log_analysis_results.txt`.

---

# 1. UTC interval, valid/malformed/duplicate lines

## Commands

```bash
./analyze_logs.py | tee log_analysis_results.txt
```

Exact duplicate verification for the application log:

```bash
python3 - <<'PY'
import json
from collections import Counter, defaultdict

path = "logs/application.log"

event_counts = Counter()
request_events = defaultdict(list)
raw_lines = Counter()

with open(path, encoding="utf-8") as f:
    for line in f:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_counts[r.get("event")] += 1
        request_events[r["request_id"]].append(r)
        raw_lines[line.rstrip("\n")] += 1

exact_duplicate_lines = sum(
    count - 1 for count in raw_lines.values()
    if count > 1
)

print("event counts:", dict(event_counts))
print("valid lines:", sum(event_counts.values()))
print("distinct request IDs:", len(request_events))
print(
    "request IDs with multiple events:",
    sum(1 for records in request_events.values() if len(records) > 1)
)
print("exact duplicate physical lines:", exact_duplicate_lines)
PY
```

## Results

| File              | Valid | Malformed | Exact duplicate lines | UTC interval                                            |
| ----------------- | ----: | --------: | --------------------: | ------------------------------------------------------- |
| `access.log`      |   725 |         1 |                     5 | `2026-08-20T11:00:00.015Z` – `2026-08-20T11:29:57.578Z` |
| `application.log` |   729 |         1 |                     2 | `2026-08-20T11:00:00.015Z` – `2026-08-20T11:29:57.578Z` |
| `error.log`       |    67 |         0 |                     0 | `2026-08-20T11:05:02Z` – `2026-08-20T11:26:47Z`         |

The `error.log` also contains one non-request notice at `2026/08/20 11:30:00`:

```text
[notice] log collector rotated stream
```

This line was excluded from request-error parsing because it contains no `request_id`.

The application log contains 682 `http_request` events and 47 `dependency_error` events. The 47 dependency-error events legitimately share request IDs with HTTP request events and therefore are not duplicate physical log records.

---

# 2. Distinct client requests and deduplication

## Result

There were:

```text
725 valid access-log records
720 distinct access request IDs
5 exact duplicate access records
```

Therefore, **720 distinct client request IDs** are represented in the access log.

The five repeated access records were treated as exact duplicate records because their relevant fields were identical. They were not counted as retries.

For the application log:

```text
729 valid records
680 distinct request IDs
```

This difference does not represent 49 duplicate requests. The application log contains multiple event types for the same request:

```text
http_request + dependency_error: 47 request IDs
http_request + http_request: 2 request IDs
```

The application log therefore must not be used directly as the client-request denominator.

## Retry handling

The retry test grouped access records by `request_id` and compared:

* timestamp
* upstream
* status
* upstream status
* request time

A retry candidate was only reported when the same request ID had multiple non-identical records.

Result:

```text
Potential retry request IDs: 0
```

Therefore, there is **no evidence of multiple non-identical access-log records representing the same client request**.

NGINX error logs provide separate evidence of upstream recovery: 19 `connect() failed` events correspond to access-log requests whose final status was HTTP 200. These are treated as NGINX upstream recovery/failover evidence, not as duplicate access-log requests.

---

# 3. Final client status counts and error rate

## Result

```text
200: 620
404: 10
502: 40
503: 47
504: 8
```

Total valid access-log responses:

```text
725
```

Total 5xx responses:

```text
95
```

The 5xx error rate using all valid access-log responses as the denominator is:

```text
95 / 725 = 13.10%
```

Therefore:

**5xx error rate = 13.10% of valid access-log response records.**

The 404 responses are not included in the 5xx error rate.

---

# 4. Failure paths, time windows and backends

## Failures by path

The 95 5xx responses were distributed as:

```text
/records: 26
/counter: 26
/ready: 23
/health: 10
/: 10
```

The `/missing` path had 10 failures in the broader `status >= 400` analysis, but these were HTTP 404 responses rather than 5xx failures.

## Failures by time window

The 5xx counts by UTC minute were:

```text
11:05: 8
11:06: 8
11:07: 8
11:08: 8
11:09: 8

11:12: 8
11:13: 7
11:14: 8
11:15: 8

11:20: 8
11:21: 8

11:25: 4
11:26: 4
```

Total:

```text
95
```

## Failures by upstream

```text
172.23.0.12:8080: 68
172.23.0.11:8080: 27
```

The first major failure period was concentrated on `172.23.0.12:8080`.

Status and upstream correlation showed:

```text
502 -> 172.23.0.12:8080: 40
503 -> 172.23.0.11:8080: 23
503 -> 172.23.0.12:8080: 24
504 -> 172.23.0.11:8080: 4
504 -> 172.23.0.12:8080: 4
```

Thus all 40 HTTP 502 responses were associated with `172.23.0.12:8080`.

---

# 5. Median and p95 client latency

Latency was taken from `access.log` `request_time`, converted from seconds to milliseconds.

Result:

```text
count=725
median=54.00 ms
p95=2001.00 ms
```

Percentile method:

```text
linear interpolation between nearest ranks
```

Therefore:

* **Median client latency: 54.00 ms**
* **p95 client latency: 2001.00 ms**

The reported latency statistics use all 725 valid access-log records, including the five exact duplicate records. The percentile denominator is therefore explicitly the 725 valid access-log records.

---

# 6. Upstream retries

The access log was checked for the same `request_id` appearing with multiple non-identical upstream attempts.

Command/result:

```text
Potential retry request IDs: 0
```

The analyzer therefore reports:

```text
retried request IDs=0
succeeded after retrying=0
```

There is, however, a separate NGINX-level recovery signal.

Correlation of `error.log` with `access.log` produced:

```text
connect() failed -> HTTP 200: 19
connect() failed -> HTTP 502: 40
upstream timed out -> HTTP 504: 8
```

The 19 `connect() failed -> HTTP 200` cases show that NGINX experienced an upstream connection failure but the corresponding client request eventually received HTTP 200.

Because the access log contains only the final client-facing record for those requests, these 19 events cannot be represented as duplicate access records. They are therefore described as **upstream recovery/failover evidence**, not as access-log retries.

---

# 7. Incident timeline

All times below are UTC.

## 11:00 – normal traffic begins

The access and application logs contain successful requests such as:

```text
lab-000002
2026-08-20T11:00:02.532Z
GET /health
HTTP 200
app-02
```

and:

```text
lab-000003
2026-08-20T11:00:05.049Z
GET /health
HTTP 200
app-01
```

This demonstrates that both application instances were serving requests at the beginning of the observed interval.

## 11:05 – app-02 connectivity failures

NGINX begins reporting:

```text
connect() failed (111: Connection refused)
```

for upstream:

```text
172.23.0.12:8080
```

The corresponding client responses are HTTP 502.

The first correlated example is:

```text
request_id=lab-000122
access timestamp=2026-08-20T11:05:02.503Z
path=/health
status=502
upstream=172.23.0.12:8080
```

The error log contains the corresponding connection-refused event at `11:05:02`.

The 502 pattern continues from approximately 11:05 through 11:09, producing 40 HTTP 502 responses.

## 11:12 – Redis dependency degradation

Application logs begin reporting dependency errors involving Redis.

Example:

```text
request_id=lab-000292
timestamp=2026-08-20T11:12:09.524Z
instance_id=app-02
dependency=redis
error_type=TimeoutError
```

The application analysis found:

```text
31 TimeoutError
```

and the dependency errors occurred on both application instances.

## 11:15 – continuing dependency failures

The dependency-error activity continues through approximately 11:15.

The 5xx timeline shows:

```text
11:12: 8
11:13: 7
11:14: 8
11:15: 8
```

## 11:20 – PostgreSQL authentication failures

Application logs show PostgreSQL authentication failures.

Example:

```text
request_id=lab-000484
timestamp=2026-08-20T11:20:07.540Z
instance_id=app-02
dependency=postgres
error_type=InvalidPassword
```

The application analysis found:

```text
16 InvalidPassword
```

The dependency was explicitly identified as PostgreSQL.

## 11:20–11:21 – continued 5xx responses

The access log records:

```text
11:20: 8
11:21: 8
```

5xx responses.

The PostgreSQL authentication failures are evidence of a dependency/configuration problem affecting application requests during this period.

## 11:20–11:26 – upstream timeouts

The NGINX error log contains:

```text
upstream timed out
```

for 8 requests.

The corresponding access-log responses are:

```text
504: 8
```

These are split evenly between the two upstream addresses:

```text
172.23.0.11:8080: 4
172.23.0.12:8080: 4
```

## 11:25–11:26 – final observed 5xx window

The final 5xx responses occur at:

```text
11:25: 4
11:26: 4
```

The NGINX request-error interval ends at approximately `11:26:47Z`.

The access/application logs continue until approximately `11:29:57Z`.

## 11:30 – non-request log notice

`error.log` contains:

```text
log collector rotated stream
```

at `11:30:00`.

This was excluded from request-error analysis because it has no request ID and does not represent a client request.

---

# 8. Correlated failed and successful requests

## Failed request

Request ID:

```text
lab-000122
```

Access log:

```text
timestamp=2026-08-20T11:05:02.503Z
method=GET
path=/health
status=502
upstream=172.23.0.12:8080
```

Corresponding NGINX error log:

```text
2026/08/20 11:05:02
connect() failed (111: Connection refused)
upstream=http://172.23.0.12:8080/health
request_id=lab-000122
```

There is no corresponding application `http_request` record for this failed request in the parsed application log. This is consistent with the failure occurring while NGINX was trying to establish the upstream connection.

## Successful request

Request ID:

```text
lab-000002
```

Application log:

```text
timestamp=2026-08-20T11:00:02.532Z
instance_id=app-02
method=GET
path=/health
status=200
duration_ms=32.0
```

Access log:

```text
timestamp=2026-08-20T11:00:02.532Z
status=200
upstream=172.23.0.12:8080
upstream_status=200
request_time=0.032
```

The matching request ID and timestamp demonstrate correlation between the client-facing NGINX record and the application record.

---

# 9. Proxy/connectivity versus dependency/application errors

## Proxy/upstream connectivity evidence

The clearest proxy/connectivity problem is:

```text
connect() failed (111: Connection refused)
```

This occurred 59 times in `error.log`.

Correlation with the access log gives:

```text
connect() failed -> HTTP 502: 40
connect() failed -> HTTP 200: 19
```

The 40 HTTP 502 responses therefore directly correlate with failed NGINX-to-upstream connection attempts.

The fact that all 40 502 responses targeted `172.23.0.12:8080` is strong evidence of an upstream-specific connectivity problem during that period.

There are also 8:

```text
upstream timed out
```

events corresponding to 8 HTTP 504 responses.

## Dependency/application evidence

The application log contains 47 `dependency_error` events:

```text
TimeoutError: 31
InvalidPassword: 16
```

The Redis example explicitly identifies:

```text
dependency=redis
error_type=TimeoutError
```

The PostgreSQL example explicitly identifies:

```text
dependency=postgres
error_type=InvalidPassword
```

These records demonstrate application-level dependency failures rather than an NGINX connection refusal.

The two categories should therefore be kept separate:

* `502 + connect() failed` → NGINX/upstream connectivity failure.
* `504 + upstream timed out` → upstream response timeout.
* `Redis TimeoutError` → application dependency timeout.
* `PostgreSQL InvalidPassword` → application dependency authentication failure.

---

# 10. What the logs do not prove

The logs provide strong evidence about symptoms and correlations, but they do not prove every underlying root cause.

## What is not proven

### Why app-02 refused connections

The logs prove that NGINX received `connection refused` when connecting to `172.23.0.12:8080`.

They do not prove whether:

* the container was stopped,
* the application process had crashed,
* the process was not listening,
* the application was restarting,
* or another network/runtime condition caused the refusal.

### Why Redis timed out

The application logs prove Redis `TimeoutError` events.

They do not prove whether Redis itself was overloaded, unavailable, network-isolated, blocked, restarting, or otherwise unable to respond.

### Why PostgreSQL authentication failed

The application logs prove `InvalidPassword` for the PostgreSQL dependency.

They do not prove:

* which configuration source contained the incorrect password,
* who changed the credentials,
* whether PostgreSQL's password changed,
* or whether the application configuration was stale.

### Exact cause of the 504 timeouts

The NGINX log proves upstream timeout events and the access log proves HTTP 504 responses.

The logs alone do not prove whether the application was slow because of Redis, PostgreSQL, CPU/memory pressure, a slow query, application code, or another dependency.

## Checks to perform in a running environment

If this incident were occurring in the live environment, the next checks would include:

```bash
docker compose ps
docker compose logs --tail=200 app-01 app-02
docker compose logs --tail=200 nginx
docker compose logs --tail=200 redis
docker compose logs --tail=200 postgres
```

Check application listening state:

```bash
docker exec app-01 ss -lntp
docker exec app-02 ss -lntp
```

Check Redis:

```bash
docker exec redis redis-cli ping
```

Check PostgreSQL:

```bash
docker exec postgres pg_isready -U barq_app -d barq_tasks
```

Check application readiness:

```bash
curl -i http://localhost:8080/ready
```

Check container health/restarts:

```bash
docker inspect app-01 --format '{{json .State}}'
docker inspect app-02 --format '{{json .State}}'
docker inspect redis --format '{{json .State}}'
docker inspect postgres --format '{{json .State}}'
```

The goal would be to correlate runtime/container state, application logs, dependency health, restart history, resource usage, and network connectivity with the historical symptoms.

---

# Commands / scripts used

The primary reproducible analysis command was:

```bash
./analyze_logs.py | tee log_analysis_results.txt
```

Additional verification commands included:

```bash
python3 - <<'PY'
# Verify application dependency errors and their dependency/error type.
import json

with open("logs/application.log", encoding="utf-8") as f:
    for line in f:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue

        if r.get("event") == "dependency_error":
            print(json.dumps(r, indent=2))
            break
PY
```

5xx counts by path:

```bash
python3 - <<'PY'
import json
from collections import Counter

c = Counter()

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue

        if int(r["status"]) >= 500:
            c[r["path"]] += 1

print("5xx failures by path:")
for path, count in c.most_common():
    print(f"{path}: {count}")
PY
```

NGINX error-to-access correlation:

```bash
python3 - <<'PY'
import json
import re
from collections import Counter

access = {}

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        access[r["request_id"]] = r

error_re = re.compile(r"request_id=(?P<id>[^,]+)")
counts = Counter()

with open("logs/error.log", encoding="utf-8") as f:
    for line in f:
        m = error_re.search(line)
        if not m:
            continue

        rid = m.group("id")
        status = access.get(rid, {}).get("status", "NO_ACCESS_RECORD")

        if "connect() failed" in line:
            error_type = "connect() failed"
        elif "upstream timed out" in line:
            error_type = "upstream timed out"
        else:
            error_type = "other"

        counts[(error_type, status)] += 1

for (error_type, status), count in sorted(counts.items()):
    print(f"{error_type} -> HTTP {status}: {count}")
PY
```

Retry detection:

```bash
python3 - <<'PY'
import json
from collections import defaultdict

groups = defaultdict(list)

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        groups[r["request_id"]].append(r)

found = 0

for request_id, rows in groups.items():
    unique = {
        (
            r["timestamp"],
            r["upstream"],
            r["status"],
            r["upstream_status"],
            r["request_time"],
        )
        for r in rows
    }

    if len(unique) > 1:
        found += 1

print(f"Potential retry request IDs: {found}")
PY
```

---

# Conclusions and limits

The historical incident shows several distinct failure modes rather than one conclusively proven root cause.

The earliest major failure was concentrated on `172.23.0.12:8080`, where NGINX recorded connection refusals and returned 40 HTTP 502 responses. Later, application logs recorded Redis timeouts and PostgreSQL authentication failures. NGINX subsequently recorded upstream timeouts corresponding to HTTP 504 responses.

The strongest conclusions supported directly by the logs are:

1. `app-02`'s upstream address experienced connection failures during the 11:05–11:09 UTC period.
2. Redis experienced application-level timeout errors.
3. PostgreSQL experienced application-level password authentication errors.
4. NGINX experienced upstream response timeouts producing HTTP 504 responses.
5. The client-facing 5xx rate was 13.10% using all 725 valid access-log records as the denominator.
6. There is no evidence of non-identical duplicate access records representing retries.
7. NGINX did record 19 upstream connection failures for requests whose final client response was HTTP 200, indicating upstream recovery/failover during those requests.
8. The logs do not independently prove the underlying operational cause of the backend, Redis, or PostgreSQL failures.

The original supplied log files remain unchanged. Analysis exclusions and duplicate handling are implemented in `analyze_logs.py`, and the generated analysis output is stored in `log_analysis_results.txt`.
