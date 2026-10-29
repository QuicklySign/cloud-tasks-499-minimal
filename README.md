# Cloud Tasks CreateTask 499 CANCELLED

`create_task` intermittently fails with `499 CANCELLED` within about 25 ms. The failures come in short bursts,
8–40 seconds after a 5-minute mark, nearly always after a quarter-hour (:00, :15, :30, :45). Cloud Monitoring
shows no 499s for CreateTask, and the failed tasks are not created.

`repro.py` is the documented `google-cloud-tasks` sample (one shared `CloudTasksClient`, library defaults, no
retry) called at a steady rate from a few threads. Each task carries an `X-Repro-Id` header, so the queue can be
checked afterwards for tasks whose CreateTask call failed.

## Run it

Needs a project with the Cloud Tasks API enabled. From Cloud Shell:

```sh
gcloud config set project PROJECT_ID
gcloud tasks queues create repro-499 --location=europe-west1
gcloud tasks queues pause repro-499 --location=europe-west1   # tasks stay listed and are never dispatched

pip install -r requirements.txt
python repro.py run --project PROJECT_ID --minutes 60         # 100 CreateTask/s, prints each failure
python repro.py check --project PROJECT_ID                    # were any failed tasks created anyway?
```

Run for at least an hour: not every quarter-hour produces a burst. Failures are printed as they happen and
written to `errors.jsonl`, with UTC timestamps to the millisecond.

Clean up with `gcloud tasks queues delete repro-499 --location=europe-west1`.

## Versions

`google-cloud-tasks` 2.25.0, `google-api-core` 2.39.0, `grpcio` 1.84.0.
