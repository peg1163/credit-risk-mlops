FROM python:3.11-slim

# Version of this training image, not of the model. See ADR-0009 and ADR-0010.
ARG IMAGE_VERSION=local

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/data-science/src:/app \
    IMAGE_VERSION=${IMAGE_VERSION}

WORKDIR /app
COPY data-science/requirements-training.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY data-science/src /app/data-science/src
COPY data-science/configs /app/data-science/configs
COPY mlops/monitoring/quality.py mlops/monitoring/build_reference_profile.py /app/mlops/monitoring/
COPY mlops/experiments /app/mlops/experiments
COPY mlops/sagemaker/train.py mlops/sagemaker/package_model.py /app/mlops/sagemaker/

# Runs as root: SageMaker mounts /opt/ml owned by root and the job must write
# /opt/ml/model and /opt/ml/output. The container lives only for the job and
# its permissions come from the training execution role, not from this user.
# SageMaker passes "train" as the argument; the entrypoint ignores it.
ENTRYPOINT ["python", "-m", "mlops.sagemaker.train"]
