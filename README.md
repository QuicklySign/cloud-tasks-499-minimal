# Cloud Tasks CreateTask 499 CANCELLED

`create_task` intermittently fails with `499 CANCELLED` within about 25 ms. The failures come in short bursts,
8–40 seconds after a 5-minute mark, nearly always after a quarter-hour (:00, :15, :30, :45). Cloud Monitoring
shows no 499s for CreateTask, and the failed tasks are not created.

`repro.py` is the documented `google-cloud-tasks` sample (one shared `CloudTasksClient`, library defaults, no
retry) called at a steady rate from a few threads. Each task carries an `X-Repro-Id` header, so the queue can be
checked afterwards for tasks whose CreateTask call failed.

## Run it as a Cloud Run job

```sh
PROJECT_ID=your-project
REGION=europe-west1
gcloud config set project $PROJECT_ID
gcloud services enable cloudtasks.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# The job and the source build run as the default compute service account.
SA=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com
for role in cloudtasks.enqueuer cloudtasks.viewer run.builder; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=roles/$role --condition=None
done

# A paused queue: tasks stay listed and are never dispatched.
gcloud tasks queues create repro-499 --location=$REGION
gcloud tasks queues pause repro-499 --location=$REGION

# 100 CreateTask/s for 3 hours, then a check of the queue.
gcloud run jobs deploy repro-499 --source . --region=$REGION --task-timeout=4h --max-retries=0 \
  --args=run,--project,$PROJECT_ID,--location,$REGION,--minutes,180,--check
gcloud run jobs execute repro-499 --region=$REGION
```

Run for at least an hour: not every quarter-hour produces a burst. Read the results from the job's logs:

```sh
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="repro-499"
  AND (textPayload:"CreateTask failed" OR textPayload:"listed" OR textPayload:"created anyway" OR textPayload:"done")' \
  --format='value(textPayload)' --order=asc --freshness=1d
```

Each failure is one `CreateTask failed <UTC time> <code> <ms> id=<X-Repro-Id>` line. The last lines say how many
calls succeeded and failed, and how many of the failed tasks exist in the queue.

Clean up with `gcloud run jobs delete repro-499 --region=$REGION` and
`gcloud tasks queues delete repro-499 --location=$REGION`.

## Run it locally

```sh
pip install -r requirements.txt
python repro.py run --project $PROJECT_ID --minutes 60 --check
```

Failures are also written to `errors.jsonl`; `python repro.py check --project $PROJECT_ID` re-checks the queue.

## Versions

`google-cloud-tasks` 2.25.0, `google-api-core` 2.39.0, `grpcio` 1.84.0, Python 3.13.
