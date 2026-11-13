FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/data-science/src

WORKDIR /app
COPY data-science/requirements-inference.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && groupadd --system appgroup \
    && useradd --system --gid appgroup --no-create-home appuser
COPY data-science/src /app/data-science/src
USER appuser
EXPOSE 8080
ENTRYPOINT ["python", "-m", "credit_risk.sagemaker_serve"]
