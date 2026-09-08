FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/data-science/src

WORKDIR /app

COPY data-science/requirements-inference.txt \
     /app/data-science/requirements-inference.txt

RUN pip install --no-cache-dir \
    -r /app/data-science/requirements-inference.txt

COPY data-science/src \
     /app/data-science/src

COPY data-science/predict.py \
     /app/data-science/predict.py

COPY data-science/configs \
     /app/data-science/configs

RUN mkdir -p \
      /app/data-science/artifacts \
      /app/input \
      /app/output \
    && groupadd --system appgroup \
    && useradd --system \
         --gid appgroup \
         --home-dir /app \
         --no-create-home \
         appuser \
    && chown -R appuser:appgroup \
         /app/data-science/artifacts \
         /app/output

USER appuser

ENTRYPOINT ["python", "/app/data-science/predict.py"]
