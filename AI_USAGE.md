# AI usage disclosure

- Tool/model: Claude & Chatgbt.
- Purpose: Used as a troubleshooting mentor throughout Parts 1-3 —
  helped structure the investigation approach (symptom -> hypothesis -> command -> result), suggested categories of likely misconfigurations
  to check (networking, ports, healthchecks, secrets, persistence)
  without providing direct fixed file contents, and helped draft
  documentation structure/wording for decisions.md, security_review.md.
- What I changed or rejected: every suggested hypothesis was verified by me against actual command output (docker compose config, docker compose up logs, curl responses, docker compose ps status) before being accepted as a root cause; I made the actual file edits and ran/interpreted the retests myself; I chose to leave max_fails=0 unchanged rather than apply a suggested production tuning, to stay within the assessment's required scope.
- How I independently verified it: every fix was retested against the running environment (docker compose ps health status, curl to /health//ready/records/counter, docker compose logs, validate.py and failure_test.py output) before being committed; commit messages record the specific verification evidence for each change.
