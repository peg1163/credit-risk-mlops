"""Daily Lambda: copy one UTC day of endpoint capture from CloudWatch Logs to S3.

It also publishes the capture gap: endpoint invocations according to SageMaker
minus the distinct requests found in the capture. Any value above zero means a
request was answered but not stored. See ADR-0006 and ADR-0008.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone

NAMESPACE = "CreditRisk/Endpoint"
CAPTURE_EVENT = "inference_capture"
FILTER_PATTERN = '{ $.event = "inference_capture" }'


def target_day(event: dict | None, now: datetime) -> date:
    if event and event.get("date"):
        return date.fromisoformat(event["date"])
    return (now.astimezone(timezone.utc) - timedelta(days=1)).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def capture_key(day: date) -> str:
    return f"endpoint-capture/date={day.isoformat()}/capture.jsonl"


def parse_messages(messages: list[str]) -> list[dict]:
    """Keep capture lines only, once each, ordered by capture time."""
    seen, lines = set(), []
    for message in messages:
        try:
            line = json.loads(message)
        except json.JSONDecodeError:
            continue
        if not isinstance(line, dict) or line.get("event") != CAPTURE_EVENT:
            continue
        key = (line.get("request_id"), line.get("record_index"))
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return sorted(lines, key=lambda line: (line.get("captured_at", ""), line.get("record_index") or 0))


def summarize(lines: list[dict], invocations: float) -> dict:
    requests = {line["request_id"] for line in lines}
    synthetic = {line["request_id"] for line in lines if line.get("synthetic")}
    return {
        "captured_lines": len(lines),
        "captured_requests": len(requests),
        "synthetic_requests": len(synthetic),
        "real_requests": len(requests - synthetic),
        "invocations": int(invocations),
        "capture_gap": int(invocations) - len(requests),
    }


def read_log_messages(logs, log_group: str, start: datetime, end: datetime) -> list[str]:
    messages = []
    paginator = logs.get_paginator("filter_log_events")
    try:
        pages = paginator.paginate(
            logGroupName=log_group,
            startTime=int(start.timestamp() * 1000),
            endTime=int(end.timestamp() * 1000) - 1,
            filterPattern=FILTER_PATTERN,
        )
        for page in pages:
            messages.extend(event["message"] for event in page.get("events", []))
    except logs.exceptions.ResourceNotFoundException:
        return []
    return messages


def endpoint_invocations(cloudwatch, endpoint: str, start: datetime, end: datetime) -> float:
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/SageMaker",
        MetricName="Invocations",
        Dimensions=[{"Name": "EndpointName", "Value": endpoint}, {"Name": "VariantName", "Value": "AllTraffic"}],
        StartTime=start,
        EndTime=end,
        Period=86400,
        Statistics=["Sum"],
    )
    return sum(point["Sum"] for point in response.get("Datapoints", []))



def client(name: str):
    import boto3  # available in the Lambda runtime; tests pass fake clients

    return boto3.client(name)

def handler(event, context, logs=None, cloudwatch=None, s3=None, now: datetime | None = None):
    endpoint = os.environ["ENDPOINT_NAME"]
    bucket = os.environ["DATA_BUCKET"]
    log_group = os.environ["CAPTURE_LOG_GROUP"]
    logs = logs or client("logs")
    cloudwatch = cloudwatch or client("cloudwatch")
    s3 = s3 or client("s3")

    day = target_day(event, now or datetime.now(timezone.utc))
    start, end = day_bounds(day)
    lines = parse_messages(read_log_messages(logs, log_group, start, end))
    summary = summarize(lines, endpoint_invocations(cloudwatch, endpoint, start, end))

    body = "".join(json.dumps(line, separators=(",", ":")) + "\n" for line in lines)
    s3.put_object(
        Bucket=bucket,
        Key=capture_key(day),
        Body=body.encode(),
        ContentType="application/jsonlines",
        ServerSideEncryption="AES256",
    )
    dimensions = [{"Name": "EndpointName", "Value": endpoint}]
    cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[
            {"MetricName": "CaptureGap", "Dimensions": dimensions, "Value": float(summary["capture_gap"]), "Unit": "Count"},
            {"MetricName": "CapturedRequests", "Dimensions": dimensions, "Value": float(summary["captured_requests"]), "Unit": "Count"},
        ],
    )
    result = {"date": day.isoformat(), "key": capture_key(day), **summary}
    print(json.dumps(result))
    return result
