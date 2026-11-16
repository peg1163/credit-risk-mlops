"""Scheduled Lambda that proves the endpoint answers, even without real traffic.

The request carries the CustomAttributes marker ``synthetic=canary`` so the
capture lines it produces are excluded from drift. See ADR-0006.
"""

from __future__ import annotations

import json
import os
import time

NAMESPACE = "CreditRisk/Endpoint"
CANARY_ATTRIBUTE = "synthetic=canary"


def check_response(body: bytes) -> bool:
    result = json.loads(body)
    score = result.get("score")
    return isinstance(score, (int, float)) and 0.0 <= score <= 1.0 and result.get("decision") in (0, 1)



def client(name: str):
    import boto3  # available in the Lambda runtime; tests pass fake clients

    return boto3.client(name)

def handler(event, context, runtime=None, cloudwatch=None):
    endpoint = os.environ["ENDPOINT_NAME"]
    runtime = runtime or client("sagemaker-runtime")
    cloudwatch = cloudwatch or client("cloudwatch")
    started = time.perf_counter()
    ok, error = False, None
    try:
        response = runtime.invoke_endpoint(
            EndpointName=endpoint,
            ContentType="application/json",
            Accept="application/json",
            CustomAttributes=CANARY_ATTRIBUTE,
            Body=os.environ["CANARY_PAYLOAD"].encode(),
        )
        ok = check_response(response["Body"].read())
        if not ok:
            error = "Response failed the contract check"
    except Exception as exc:  # any failure is an unavailable endpoint for the canary
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = (time.perf_counter() - started) * 1000
    dimensions = [{"Name": "EndpointName", "Value": endpoint}]
    cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[
            {"MetricName": "CanaryOK", "Dimensions": dimensions, "Value": 1.0 if ok else 0.0, "Unit": "Count"},
            {"MetricName": "CanaryLatency", "Dimensions": dimensions, "Value": latency_ms, "Unit": "Milliseconds"},
        ],
    )
    result = {"endpoint": endpoint, "ok": ok, "latency_ms": round(latency_ms, 1), "error": error}
    print(json.dumps(result))
    return result
