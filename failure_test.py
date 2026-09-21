#!/usr/bin/env python3

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8080"
BACKEND = "app-02"
REQUEST_COUNT = 20
REQUEST_TIMEOUT = 2


def run(cmd, timeout=20):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"


def request(path="/health"):
    try:
        start = time.monotonic()

        req = urllib.request.Request(
            BASE_URL + path,
            method="GET",
            headers={"Connection": "close"},
        )

        with urllib.request.urlopen(
            req,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            body = response.read().decode()
            elapsed = time.monotonic() - start

            return {
                "ok": response.status == 200,
                "status": response.status,
                "body": body,
                "elapsed": elapsed,
            }

    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "body": "",
            "error": str(exc),
        }

    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "body": "",
            "error": str(exc),
        }


def run_traffic(count):
    results = []

    for _ in range(count):
        results.append(request("/health"))

    return results


def summarize(results):
    status_counts = {}
    instances = {}
    errors = 0
    total_time = 0.0

    for result in results:
        status = str(result.get("status"))

        status_counts[status] = status_counts.get(status, 0) + 1

        if not result["ok"]:
            errors += 1

        total_time += result.get("elapsed", 0)

        if result["body"]:
            try:
                payload = json.loads(result["body"])
                instance = payload.get("instance_id")

                if instance:
                    instances[instance] = instances.get(instance, 0) + 1

            except json.JSONDecodeError:
                pass

    average_time = total_time / len(results) if results else 0

    return {
        "total": len(results),
        "errors": errors,
        "status_counts": status_counts,
        "instances": instances,
        "average_time_ms": round(average_time * 1000, 2),
    }


def container_running(name):
    rc, out, _ = run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name]
    )

    return rc == 0 and out == "true"


def wait_for_backend(timeout=30):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if container_running(BACKEND):
            return True

        time.sleep(1)

    return False


def wait_for_backend_health(timeout=30):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        rc, out, _ = run(
            [
                "docker",
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}",
                BACKEND,
            ]
        )

        if rc == 0 and out == "healthy":
            return True

        time.sleep(1)

    return False


def main():
    print("=== BARQ Backend Failure / Recovery Test ===")
    print(f"Target backend: {BACKEND}")
    print(f"Requests per phase: {REQUEST_COUNT}")
    print(f"Request timeout: {REQUEST_TIMEOUT}s")

    backend_was_stopped = False

    # ------------------------------------------------------------
    # Baseline
    # ------------------------------------------------------------
    print("\n--- Baseline traffic ---")

    baseline = run_traffic(REQUEST_COUNT)
    baseline_summary = summarize(baseline)

    print(json.dumps(baseline_summary, indent=2))

    if baseline_summary["errors"]:
        print("FAIL: baseline traffic already has errors")
        sys.exit(1)

    if "app-01" not in baseline_summary["instances"]:
        print("FAIL: baseline did not reach app-01")
        sys.exit(1)

    if "app-02" not in baseline_summary["instances"]:
        print("FAIL: baseline did not reach app-02")
        sys.exit(1)

    print("PASS: baseline traffic reached both backends")

    # ------------------------------------------------------------
    # Stop one backend
    # ------------------------------------------------------------
    print(f"\n--- Stopping {BACKEND} ---")

    rc, out, err = run(
        ["docker", "stop", BACKEND],
        timeout=30,
    )

    if rc != 0:
        print("FAIL: could not stop backend")
        print(err or out)
        sys.exit(1)

    backend_was_stopped = True

    if container_running(BACKEND):
        print("FAIL: backend is still running")
        sys.exit(1)

    print(f"PASS: {BACKEND} stopped")

    try:
        # --------------------------------------------------------
        # Traffic while backend is down
        # --------------------------------------------------------
        print("\n--- Traffic during backend failure ---")

        failure_phase = run_traffic(REQUEST_COUNT)
        failure_summary = summarize(failure_phase)

        print(json.dumps(failure_summary, indent=2))

        if "app-01" not in failure_summary["instances"]:
            print("FAIL: surviving backend did not serve traffic")
            sys.exit(1)

        if "app-02" in failure_summary["instances"]:
            print("FAIL: stopped backend still appeared to serve traffic")
            sys.exit(1)

        if failure_summary["errors"] == 0:
            print("PASS: all traffic remained available through app-01")
        else:
            print(
                "INFO: service remained partially available, but "
                f"{failure_summary['errors']} request(s) failed"
            )

        print(
            "PASS: failure traffic was measured with bounded request timeouts"
        )

    finally:
        # --------------------------------------------------------
        # Restore backend
        # --------------------------------------------------------
        print(f"\n--- Restoring {BACKEND} ---")

        rc, out, err = run(
            ["docker", "start", BACKEND],
            timeout=30,
        )

        if rc != 0:
            print("FAIL: could not start backend")
            print(err or out)
            sys.exit(1)

        backend_was_stopped = False
        print(f"PASS: {BACKEND} start command completed")

    # ------------------------------------------------------------
    # Wait for recovery
    # ------------------------------------------------------------
    print("\n--- Waiting for backend recovery ---")

    if not wait_for_backend(timeout=30):
        print("FAIL: backend did not become running again")
        sys.exit(1)

    print(f"PASS: {BACKEND} is running again")

    if not wait_for_backend_health(timeout=30):
        print(f"FAIL: {BACKEND} did not become healthy")
        sys.exit(1)

    print(f"PASS: {BACKEND} is healthy again")

    # ------------------------------------------------------------
    # Prove recovered backend serves requests
    # ------------------------------------------------------------
    print("\n--- Proving recovered backend serves requests ---")

    recovered = False

    deadline = time.monotonic() + 30

    while time.monotonic() < deadline:
        result = request("/instance")

        if result["ok"]:
            try:
                payload = json.loads(result["body"])

                if payload.get("instance_id") == BACKEND:
                    recovered = True
                    break

            except json.JSONDecodeError:
                pass

        time.sleep(1)

    if not recovered:
        print(f"FAIL: recovered {BACKEND} did not serve /instance")
        sys.exit(1)

    print(f"PASS: recovered {BACKEND} served /instance")

    # ------------------------------------------------------------
    # Recovery traffic
    # ------------------------------------------------------------
    print("\n--- Traffic after recovery ---")

    recovery_phase = run_traffic(REQUEST_COUNT)
    recovery_summary = summarize(recovery_phase)

    print(json.dumps(recovery_summary, indent=2))

    if recovery_summary["errors"]:
        print(
            "FAIL: recovery traffic contains "
            f"{recovery_summary['errors']} error(s)"
        )
        sys.exit(1)

    if BACKEND not in recovery_summary["instances"]:
        print("FAIL: recovered backend did not receive traffic")
        sys.exit(1)

    print("PASS: recovered backend received traffic")

    print("\n=== Failure test result ===")
    print(
        "PASS: backend failure, availability measurement, "
        "restoration and recovery verified"
    )

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nFAIL: failure test interrupted")
        sys.exit(1)
