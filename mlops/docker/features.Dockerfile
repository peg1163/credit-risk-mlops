FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/data-science/src
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY data-science/requirements-features.txt /app/data-science/requirements-features.txt

RUN pip install --no-cache-dir --requirement /app/data-science/requirements-features.txt

COPY data-science/src /app/data-science/src
COPY data-science/build_features.py /app/data-science/build_features.py
COPY data-science/configs /app/data-science/configs

RUN mkdir -p /app/data-science/data
RUN groupadd --system appgroup
RUN useradd --system --gid appgroup --home-dir /tmp --no-create-home appuser
RUN chown appuser:appgroup /app/data-science/data

USER appuser

ENTRYPOINT ["python", "/app/data-science/build_features.py"]
