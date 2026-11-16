# ADR-0010: Entrenamiento y seguimiento de experimentos en SageMaker

- Estado: Propuesto
- Fecha: 2026-11-16
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

Hoy el modelo se entrena en una laptop con `credit_risk.modeling`. MLflow
guarda las corridas en `data-science/artifacts/mlruns/`, que no se versiona.
El `model.tar.gz` del endpoint se arma y se sube a S3 a mano. Nada en AWS
registra qué datos, qué imagen y qué hiperparámetros produjeron el modelo que
sirve el endpoint (ADR-0005).

Además hace falta repetir experimentos de reentrenamiento y drift (la
simulación de reentreno cada 6 meses) en un entorno que no dependa de una
máquina personal.

Hechos verificados en la documentación de AWS y en el provider el 2026-11-16:

- Las **MLflow Apps** de SageMaker son serverless y no tienen cargo adicional;
  se paga el almacenamiento de artefactos en S3. Los *tracking servers*
  clásicos cobran por hora: Small ~USD 0.60/h, unas USD 430 al mes encendido.
- La API es `CreateMlflowApp`. El ARN tiene la forma
  `arn:aws:sagemaker:<región>:<cuenta>:mlflow-app/<id>`, con un id que genera
  AWS. El cliente usa el ARN como `MLFLOW_TRACKING_URI` con el plugin
  `sagemaker-mlflow`, y necesita `sagemaker:CallMlflowAppApi`.
- El provider `hashicorp/aws` 6.65 incluye `aws_sagemaker_mlflow_app`.
- Un training job cobra por segundo de instancia. En `ml.m5.large`
  (~USD 0.115/h), un entrenamiento de este modelo cuesta centavos.

## Drivers de decisión

- Trazabilidad: dataset, imagen, hiperparámetros y métricas de cada modelo
  candidato, consultables sin la laptop de nadie.
- Reproducir la simulación de reentreno con los mismos datos y el mismo código.
- Costo fijo cercano a cero en development.
- No abrir otra vía de promoción: la promoción sigue siendo un PR (ADR-0005).

## Opciones consideradas

### Opción A — Todo en local

No cuesta nada y el ciclo es rápido. No resuelve la trazabilidad, y el
historial de MLflow se pierde con la máquina.

### Opción B — Training jobs con imagen propia y MLflow App serverless

Una imagen de entrenamiento con el mismo código y las mismas versiones de
librerías que serving. Los jobs escriben un `model.tar.gz` que el endpoint
acepta sin reempaquetar y registran cada corrida en la MLflow App. Agrega una
imagen, un rol y una app.

### Opción C — Igual que B, con tracking server clásico

Mismo flujo, pero con un servidor de tamaño fijo y cargo por hora. Solo tiene
sentido si se necesita una versión fija de MLflow o una red privada.

### Opción D — Contenedor sklearn administrado por AWS (script mode)

No requiere imagen propia, pero trae otra versión de scikit-learn. Un pickle
entrenado con otra versión no tiene compatibilidad garantizada con la imagen de
serving.

## Recomendación técnica

Elegir la **Opción B**:

| Pieza | Decisión |
|---|---|
| Imagen | `mlops/docker/sagemaker-training.Dockerfile`, repositorio `<prefijo>-sagemaker-training`, tags de ADR-0009, versión en `sagemaker-training.version` |
| Entrypoint | `mlops/sagemaker/train.py`, con los modos `train` y `retraining-simulation` |
| Datos | `s3://<bucket>/datasets/modeling/<dataset_id>/modeling_dataset.parquet` |
| Salida | `s3://<bucket>/models/training-jobs/<job>/output/model.tar.gz` (modelo) y `output.tar.gz` (reportes) |
| Seguimiento | MLflow App `credit-risk-mlops-development`, con artefactos en `s3://<bucket>/mlflow/` y sin registro automático en el Model Registry |
| Lanzamiento | `mlops/sagemaker/start_training_job.py`, con credenciales de una persona |
| Rol del job | lee `datasets/`, escribe `models/training-jobs/` y `mlflow/`, y llama solo a su MLflow App |

- El modelo que produce un job **no se despliega solo**. Para promoverlo, su
  clave va en `serving-release.auto.tfvars.json` mediante un PR, igual que en
  ADR-0005.
- `model_version` del manifiesto sigue siendo el contrato de features que
  valida la imagen de serving (`0.1.0`). La identidad del candidato queda en
  `training_job_name`, `splits` y `mlflow_run_id` del mismo manifiesto.
- El rol del job no puede escribir `models/version=*/`, donde vive el campeón.

## Resolución del propietario

- Decisión: [ ] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida:
- Justificación:
- Condiciones o cambios solicitados:
- Fecha de decisión:

## Consecuencias

### Positivas

- Cada candidato y cada simulación quedan en MLflow, con el nombre del job, el
  digest de la imagen y el URI del dataset.
- El job y la laptop corren el mismo código: `train.py` es la misma función que
  `modeling.py`, y la simulación es la misma en ambos lados.
- Sin costo fijo nuevo: la app es serverless y el job se apaga al terminar.

### Negativas y compromisos

- Una segunda imagen que mantener. Su tamaño es de ~1 GB por `mlflow-skinny` y
  `boto3`.
- El contenedor de entrenamiento corre como root, porque SageMaker monta
  `/opt/ml` como root. Vive solo durante el job y sus permisos vienen del rol.
- El permiso de administración de la app no se puede acotar por nombre, porque
  AWS genera el id. Queda acotado a `mlflow-app/*` de la cuenta y región.
- El dataset se sube a S3 a mano hasta que exista la orquestación (ADR-0002).

## Validación y criterios de reversión

- Un job `train` produce un `model.tar.gz` que `load_bundle` acepta, y el mismo
  sha256 que el entrenamiento local con los mismos parámetros.
- La corrida aparece en la MLflow App con el tag `sagemaker.training_job_name`.
- `terraform test` cubre la app, el repositorio y su retención.
- Revertir: `mlflow_app_enabled = false` elimina la app y su rol; los
  artefactos en `mlflow/` y los modelos en `models/training-jobs/` se conservan.

## Referencias

- [ADR-0004](0004-almacenamiento-y-cifrado.md)
- [ADR-0005](0005-registro-y-promocion-de-modelos.md)
- [ADR-0009](0009-tags-y-retencion-de-imagenes-ecr.md)
- [CreateMlflowApp](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_CreateMlflowApp.html)
- [Permisos IAM de MLflow Apps](https://docs.aws.amazon.com/sagemaker/latest/dg/mlflow-app-setup-prerequisites-iam.html)
- [Anuncio de MLflow serverless en SageMaker AI](https://aws.amazon.com/about-aws/whats-new/2025/12/sagemaker-ai-serverless-mlflow-ai-development)
- [Precios de SageMaker AI](https://aws.amazon.com/sagemaker/ai/pricing/)
