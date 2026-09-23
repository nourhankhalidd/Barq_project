#!/usr/bin/env python3

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8080"
TIMEOUT = 3
WAIT_TIMEOUT = 60


failures = 0


def run(cmd, timeout=TIMEOUT):
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


def check(name, condition, detail=""):
    global failures

    if condition:
        print(f"PASS: {name}")
    else:
        failures += 1
        print(f"FAIL: {name}")
        if detail:
            print(f"      {detail}")


def http_get(path):
    try:
        with urllib.request.urlopen(
            BASE_URL + path,
            timeout=TIMEOUT,
        ) as response:
            body = response.read().decode()
            return response.status, body
    except Exception as exc:
        return None, str(exc)


def wait_for_public_access():
    deadline = time.time() + WAIT_TIMEOUT

    while time.time() < deadline:
        status, _ = http_get("/health")
        if status == 200:
            return True

        time.sleep(2)

    return False


def container_running(name):
    rc, out, _ = run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name]
    )
    return rc == 0 and out == "true"


def main():
    print("=== BARQ Assessment Validation ===")

    # ------------------------------------------------------------
    # 1. Required containers
    # ------------------------------------------------------------
    print("\n--- Containers ---")

    for name in ["app-01", "app-02", "app-03","nginx", "postgres", "redis"]:
        check(
            f"container {name} is running",
            container_running(name),
        )

    # ------------------------------------------------------------
    # 2. Wait for public service
    # ------------------------------------------------------------
    print("\n--- Bounded readiness wait ---")

    check(
        "public endpoint becomes ready within 60 seconds",
        wait_for_public_access(),
    )

    # ------------------------------------------------------------
    # 3. Required public endpoints
    # ------------------------------------------------------------
    print("\n--- Public endpoints ---")

    for path in ["/", "/health", "/ready", "/instance", "/records", "/counter"]:
        status, body = http_get(path)

        check(
            f"GET {path} returns HTTP 200",
            status == 200,
            body[:200] if body else "no response",
        )

    # ------------------------------------------------------------
    # 4. Both backend instances
    # ------------------------------------------------------------
    print("\n--- Backend instances ---")

    for container in ["app-01", "app-02", "app-03"]:
        rc, out, err = run(
            [
                "docker",
                "exec",
                container,
                "python",
                "-c",
                (
                    "import urllib.request; "
                    "print(urllib.request.urlopen("
                    "'http://127.0.0.1:8080/instance', timeout=2"
                    ").read().decode())"
                ),
            ]
        )

        check(
            f"{container} serves /instance",
            rc == 0 and container in out,
            out or err,
        )

    # ------------------------------------------------------------
    # 5. PostgreSQL readiness
    # ------------------------------------------------------------
    print("\n--- PostgreSQL ---")

    rc, out, err = run(
        [
            "docker",
            "exec",
            "postgres",
            "pg_isready",
            "-U",
            "barq_app",
            "-d",
            "barq_tasks",
        ]
    )

    check(
        "PostgreSQL is ready",
        rc == 0,
        out or err,
    )

    # ------------------------------------------------------------
    # 6. Redis readiness
    # ------------------------------------------------------------
    print("\n--- Redis ---")

    rc, out, err = run(
        ["docker", "exec", "redis", "redis-cli", "ping"]
    )

    check(
        "Redis is ready",
        rc == 0 and out == "PONG",
        out or err,
    )

    # ------------------------------------------------------------
    # 7. Host port restrictions
    # ------------------------------------------------------------
    print("\n--- Host port restrictions ---")

    rc, out, err = run(
        [
            "docker",
            "ps",
            "--format",
            "{{.Names}}|{{.Ports}}",
        ]
    )

    port_map = {}

    if rc == 0:
        for line in out.splitlines():
            if "|" in line:
                name, ports = line.split("|", 1)
                port_map[name] = ports

    nginx_ports = port_map.get("nginx", "")

    check(
        "NGINX publishes host port 8080",
        "8080" in nginx_ports,
        nginx_ports,
    )

    for container in ["app-01", "app-02", "app-03", "postgres", "redis"]:
        ports = port_map.get(container, "")
        has_host_mapping = "->" in ports

        check(
            f"{container} has no published host port",
            not has_host_mapping,
            ports or "no published ports",
        )

    # ------------------------------------------------------------
    # 8. Network isolation
    # ------------------------------------------------------------
    print("\n--- Network isolation ---")

    def networks(container):
        rc, out, _ = run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}",
                container,
            ]
        )
        return set(out.split()) if rc == 0 else set()

    nginx_networks = networks("nginx")
    postgres_networks = networks("postgres")
    redis_networks = networks("redis")

    check(
        "NGINX is connected to frontend network",
        any(name.endswith("frontend") for name in nginx_networks),
        str(nginx_networks),
    )

    check(
        "PostgreSQL is connected to backend network",
        any(name.endswith("backend") for name in postgres_networks),
        str(postgres_networks),
    )

    check(
        "Redis is connected to backend network",
        any(name.endswith("backend") for name in redis_networks),
        str(redis_networks),
    )

    check(
        "NGINX is isolated from backend network",
        not any(name.endswith("backend") for name in nginx_networks),
        str(nginx_networks),
    )

    # ------------------------------------------------------------
    # 9. Named volumes
    # ------------------------------------------------------------
    print("\n--- Persistence volumes ---")

    rc, out, err = run(
        ["docker", "volume", "ls", "--format", "{{.Name}}"]
    )

    check(
        "PostgreSQL named volume exists",
        rc == 0 and any(
            "barq-assessment_postgres-data" == line
            for line in out.splitlines()
        ),
        out or err,
    )

    check(
        "Redis named volume exists",
        rc == 0 and any(
            "barq-assessment_redis-data" == line
            for line in out.splitlines()
        ),
        out or err,
    )

    # ------------------------------------------------------------
    # 10. Final result
    # ------------------------------------------------------------
    print("\n=== Validation result ===")

    if failures:
        print(f"FAIL: {failures} validation check(s) failed")
        sys.exit(1)

    print("PASS: all validation checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
