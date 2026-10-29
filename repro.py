"""Creates Cloud Tasks at a steady rate and records every CreateTask call that fails, to reproduce 499 CANCELLED.

python repro.py run   --project P --location europe-west1 --queue repro-499 [--rate 100] [--minutes 60]
python repro.py check --project P --location europe-west1 --queue repro-499
"""

import argparse
import json
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

from google.api_core import exceptions
from google.api_core.retry import Retry, if_exception_type
from google.cloud import tasks_v2

ERRORS_FILE = "errors.jsonl"
HEADER = "X-Repro-Id"


def now():
	return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def run(args, client, parent):
	counts = Counter()
	lock = threading.Lock()
	deadline = time.monotonic() + args.minutes * 60
	interval = args.workers / args.rate

	def create_one():
		repro_id = uuid.uuid4().hex
		task = tasks_v2.Task(
			http_request=tasks_v2.HttpRequest(
				http_method=tasks_v2.HttpMethod.POST, url=args.url, headers={HEADER: repro_id}
			)
		)
		started = time.monotonic()
		try:
			client.create_task(parent=parent, task=task)
			code = "OK"
		except exceptions.GoogleAPICallError as exc:
			code = exc.grpc_status_code.name if exc.grpc_status_code else type(exc).__name__
			error = {
				"time": now(),
				"code": code,
				"ms": round((time.monotonic() - started) * 1000),
				"repro_id": repro_id,
				"message": str(exc),
			}
			print(json.dumps(error), flush=True)
			with lock, open(ERRORS_FILE, "a") as f:
				f.write(json.dumps(error) + "\n")
		with lock:
			counts[code] += 1

	def worker():
		next_call = time.monotonic()
		while next_call < deadline:
			create_one()
			next_call += interval
			time.sleep(max(0.0, next_call - time.monotonic()))

	threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
	for t in threads:
		t.start()
	next_report = time.monotonic() + 60
	while any(t.is_alive() for t in threads):
		time.sleep(1)
		if time.monotonic() >= next_report:
			next_report += 60
			with lock:
				print(f"{now()} {dict(counts)}", flush=True)
	print(f"done: {dict(counts)}; failures are in {ERRORS_FILE}")


def check(args, client, parent):
	"""Lists the paused queue and reports whether any task whose CreateTask call failed was created anyway."""
	try:
		with open(ERRORS_FILE) as f:
			failed = {e["repro_id"]: e for e in map(json.loads, f)}
	except FileNotFoundError:
		failed = {}
	retry = Retry(predicate=if_exception_type(exceptions.ResourceExhausted, exceptions.ServiceUnavailable), timeout=900)
	request = {"parent": parent, "response_view": tasks_v2.Task.View.FULL, "page_size": 1000}
	listed, created = 0, []
	for task in client.list_tasks(request=request, retry=retry):
		listed += 1
		repro_id = task.http_request.headers.get(HEADER)
		if repro_id in failed:
			created.append(failed[repro_id])
	print(f"listed {listed} tasks; {len(failed)} CreateTask calls failed; {len(created)} of those tasks exist")
	for e in created:
		print(f"  created anyway: {e['time']} {e['code']} {e['repro_id']}")


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("command", choices=["run", "check"])
	parser.add_argument("--project", required=True)
	parser.add_argument("--location", default="europe-west1")
	parser.add_argument("--queue", default="repro-499")
	parser.add_argument("--rate", type=float, default=100, help="CreateTask calls per second")
	parser.add_argument("--minutes", type=float, default=60)
	parser.add_argument("--workers", type=int, default=32)
	parser.add_argument("--url", default="https://example.com/", help="never called while the queue is paused")
	args = parser.parse_args()

	client = tasks_v2.CloudTasksClient()
	parent = client.queue_path(args.project, args.location, args.queue)
	(run if args.command == "run" else check)(args, client, parent)


if __name__ == "__main__":
	main()
