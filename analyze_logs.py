#!/usr/bin/env python3

import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone


ACCESS = "logs/access.log"
ERROR = "logs/error.log"
APP = "logs/application.log"


def parse_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values, p):
    values = sorted(values)
    if not values:
        return None

    rank = (len(values) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)

    if low == high:
        return values[low]

    return values[low] + (values[high] - values[low]) * (rank - low)


def read_json_lines(path):
    records = []
    malformed = 0

    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip("\n")

            if not line.strip():
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1

    return records, malformed


def read_error_log(path):
    records = []
    malformed = 0

    pattern = re.compile(
        r'^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}).*?'
        r'request_id=(?P<request_id>[^,]+),.*?'
        r'request: "(?P<method>\S+) (?P<path>\S+) [^"]+".*?'
        r'upstream: "(?P<upstream>[^"]+)"'
    )

    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip("\n")

            if not line.strip():
                continue

            match = pattern.search(line)

            if not match:
                if "request_id=" not in line:
                    continue
                malformed += 1
                continue

            data = match.groupdict()
            data["timestamp"] = datetime.strptime(
                data["ts"], "%Y/%m/%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            records.append(data)

    return records, malformed


def duplicate_count(records):
    seen = set()
    duplicates = 0

    for record in records:
        value = json.dumps(record, sort_keys=True, default=str)

        if value in seen:
            duplicates += 1
        else:
            seen.add(value)

    return duplicates


def print_section(title):
    print(f"\n=== {title} ===")


access, access_bad = read_json_lines(ACCESS)
app, app_bad = read_json_lines(APP)
errors, error_bad = read_error_log(ERROR)

print_section("FILE COUNTS")

for name, records, malformed in [
    ("access.log", access, access_bad),
    ("application.log", app, app_bad),
    ("error.log", errors, error_bad),
]:
    timestamps = []

    for record in records:
        ts = record.get("timestamp")
        if isinstance(ts, str):
            try:
                timestamps.append(parse_ts(ts))
            except ValueError:
                pass
        elif isinstance(ts, datetime):
            timestamps.append(ts)

    print(
        f"{name}: valid={len(records)} "
        f"malformed={malformed} "
        f"duplicates={duplicate_count(records)}"
    )

    if timestamps:
        print(
            f"  interval={min(timestamps).isoformat()} "
            f"to {max(timestamps).isoformat()}"
        )


print_section("ACCESS STATUS COUNTS")

status_counts = Counter(str(r.get("status")) for r in access)
print(dict(sorted(status_counts.items())))

total_access = len(access)
errors_5xx = sum(1 for r in access if int(r.get("status", 0)) >= 500)

print(f"total client responses={total_access}")
print(f"5xx responses={errors_5xx}")
print(
    f"5xx error rate={errors_5xx / total_access * 100:.2f}% "
    f"(denominator=all valid access.log requests)"
)


print_section("DISTINCT REQUESTS")

access_ids = [r.get("request_id") for r in access if r.get("request_id")]
app_ids = [r.get("request_id") for r in app if r.get("request_id")]

print(f"access request IDs={len(access_ids)}")
print(f"distinct access request IDs={len(set(access_ids))}")
print(f"application request IDs={len(app_ids)}")
print(f"distinct application request IDs={len(set(app_ids))}")


print_section("FAILURES BY PATH")

path_failures = Counter(
    r.get("path")
    for r in access
    if int(r.get("status", 0)) >= 400
)

print(dict(path_failures.most_common()))


print_section("FAILURES BY UPSTREAM")

upstream_failures = Counter(
    r.get("upstream")
    for r in access
    if int(r.get("status", 0)) >= 500
)

print(dict(upstream_failures.most_common()))


print_section("FAILURES BY TIME WINDOW")

window_failures = Counter()

for record in access:
    status = int(record.get("status", 0))

    if status < 500:
        continue

    ts = parse_ts(record["timestamp"])
    window = ts.replace(second=0, microsecond=0)

    window_failures[window.isoformat()] += 1

print(dict(sorted(window_failures.items())))


print_section("LATENCY")

latencies = [
    float(r["request_time"])
    for r in access
    if isinstance(r.get("request_time"), (int, float))
]

print(f"count={len(latencies)}")

if latencies:
    print(f"median={statistics.median(latencies) * 1000:.2f} ms")
    print(f"p95={percentile(latencies, 0.95) * 1000:.2f} ms")
    print("percentile method=linear interpolation between nearest ranks")
    print("source=access.log request_time seconds")


print_section("UPSTREAM RETRIES")

# A retry is only reported when the same request_id has multiple
# non-identical access records. Identical repeated records are treated
# as duplicate log entries, not retries.
by_request = defaultdict(list)

for record in access:
    by_request[record.get("request_id")].append(record)

retried = {}

for request_id, records in by_request.items():
    signatures = {
        (
            r.get("timestamp"),
            r.get("upstream"),
            r.get("status"),
            r.get("upstream_status"),
            r.get("request_time"),
        )
        for r in records
    }

    if len(signatures) > 1:
        retried[request_id] = records

print(f"retried request IDs={len(retried)}")

success_after_retry = 0

for request_id, records in retried.items():
    if any(str(r.get("status", "")).startswith("2") for r in records):
        success_after_retry += 1

print(f"succeeded after retrying={success_after_retry}")
