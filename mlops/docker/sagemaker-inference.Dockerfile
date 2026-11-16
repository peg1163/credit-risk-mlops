FROM python:3.11-slim

# Version of this serving image, not of the model. See ADR-0009.
ARG IMAGE_VERSION=local

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/data-science/src \
    IMAGE_VERSION=${IMAGE_VERSION}

WORKDIR /app
COPY data-science/requirements-inference.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && groupadd --system appgroup \
    && useradd --system --gid appgroup --no-create-home appuser
COPY data-science/src /app/data-science/src
USER appuser
EXPOSE 8080
ENTRYPOINT ["python", "-m", "credit_risk.sagemaker_serve"]
