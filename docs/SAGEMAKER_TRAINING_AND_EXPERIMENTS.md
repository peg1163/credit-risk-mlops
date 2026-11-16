# Entrenamiento, simulación de reentreno y MLflow en SageMaker

Última revisión: 2026-11-16. Implementa ADR-0010, que está **Propuesto**.

## 1. Qué hay

```text
laptop ──start_training_job.py──▶ SageMaker training job (ml.m5.large, se apaga al terminar)
                                   │  imagen: <prefijo>-sagemaker-training@<digest>
  s3://<bucket>/datasets/modeling/ ┤  modo train ─────────────▶ models/training-jobs/<job>/output/model.tar.gz
                                   │  modo retraining-simulation ▶ …/output/output.tar.gz (report.json, summary.md)
                                   └─ MLFLOW_TRACKING_URI = ARN ──▶ MLflow App (serverless) ──▶ s3://<bucket>/mlflow/
laptop ──MLFLOW_TRACKING_URI = ARN──▶ misma MLflow App (corridas locales)
```

| Archivo | Contenido |
|---|---|
| `mlops/experiments/retraining.py` | Simulación de reentreno y drift mensual; corre en local o en un job |
| `mlops/sagemaker/train.py` | Entrypoint del job (`/opt/ml/...`), modos `train` y `retraining-simulation` |
| `mlops/sagemaker/start_training_job.py` | Lanza un job con boto3; `--dry-run` muestra la solicitud |
| `mlops/docker/sagemaker-training.Dockerfile` | Imagen de entrenamiento: mismas versiones que serving, más `mlflow-skinny` y `sagemaker-mlflow` |
| `infrastructure/terraform/environments/dev/training.tf` | ECR, MLflow App y su rol, rol de los jobs, grupo de logs |
| `.github/workflows/publish-training-image.yml` | Publica `v<semver>-<sha7>` desde `main` |

## 2. Resultados de la simulación (2026-11-16, local)

Comando: `PYTHONPATH=data-science/src:. python -m mlops.experiments.retraining`
(1000 remuestreos de bootstrap y semilla 42).

### Reentreno cada 6 meses frente al campeón fijo

El campeón se entrenó con datos hasta 1995-12. En cada fecha T, el retador
aprende todas las etiquetas maduras a T (`label_maturity_date <= T`). Su umbral
se elige con F1 en los últimos 12 meses maduros, y después se reajusta con
todo. Los dos puntúan los 6 meses siguientes.

| Fecha T | Cohortes evaluadas | Defaults | AUC campeón | AUC retador | Δ AUC (IC 95 %) | Δ Brier (IC 95 %) |
|---|---|---|---|---|---|---|
| 1997-01-31 | 1997-02 a 1997-07 | 33 | 0.865 | 0.834 | −0.031 [−0.100, +0.014] | +0.0025 [−0.0003, +0.0057] |
| 1997-07-31 | 1997-08 a 1998-01 | 33 | 0.862 | 0.860 | −0.003 [−0.036, +0.036] | +0.0188 [+0.0145, +0.0232] |
| 1998-01-31 | 1998-02 a 1998-06 | 31 | 0.773 | 0.759 | −0.014 [−0.068, +0.038] | +0.0316 [+0.0264, +0.0368] |
| **Política (todo junto)** | | 97 | | | −0.021 [−0.050, +0.006] | +0.0186 [+0.0158, +0.0215] |

Lectura:

- **El reentreno no mejora la discriminación.** Ningún intervalo de Δ AUC
  queda por encima de 0.
- **Empeora la calibración de forma significativa.** El intervalo de Δ Brier
  queda entero por encima de 0 en dos ventanas y en la política conjunta.
- El retador sube el recall en dos ventanas (0.09→0.21 y 0.16→0.26), pero solo
  porque elige otro umbral, no porque ordene mejor.
- El AUC del campeón cae a 0.773 en 1998-02 a 1998-06. Sigue por encima del
  umbral de investigación de 0.75, pero es la señal a vigilar.
- Con ~33 defaults por ventana, una diferencia de AUC menor a ~0.05 no se
  distingue del ruido.

Según `MONITORING_AND_RETRAINING.md`, reentrenar cada 6 meses con la misma
receta **no cumple** el criterio de promoción: no muestra un beneficio y empeora
la calibración. Lo siguiente a probar es la receta, no la frecuencia:
calibración (Platt o isotónica), quitar `class_weight="balanced"` o usar una
ventana deslizante.

### Drift mensual frente al perfil de entrenamiento

El drift se mide con los mismos buckets y el mismo PSI que la Lambda diaria.

- **`loan_age_months` deriva por construcción**: el PSI crece de 0.47 a 1.47
  porque la cartera envejece. El reporte lo muestra aparte y no lo cuenta en el
  nivel. **En producción, la alarma `endpoint-psi-material` se encendería
  siempre por esta variable**; conviene excluirla de `PsiMax` en la Lambda
  (decisión de ADR-0006).
- **Estacionalidad de enero**: `transaction_count_3m` y `balance_change_3m`
  saltan a un PSI de 0.5 a 0.65 en cada enero y febrero (1996, 1997 y 1998),
  y luego bajan.
- **`district_id`** sube de ~0.16 a ~0.42. Parte es ruido: con ~40 buckets
  (las categorías con al menos 1 % del entrenamiento, más "otros") y 200 a 600
  filas por mes, el piso de ruido es ~0.08 a 0.14, y el reporte lo
  calcula en `psi_max_noise_floor`. El resto es un cambio real en la mezcla
  geográfica.
- **El PSI del score** sube de ~0.1 a 0.45 en 1998-12. Es la señal que más
  acompaña la caída de AUC del campeón.
- Cruzando drift y reentreno: hubo drift "material" antes de cada fecha de
  reentreno y el reentreno no ayudó. **El drift no basta para decidir
  reentrenar**, que es lo que ya dice ADR-0006.

`dist/experiments/retraining/report.json` tiene todo el detalle: PSI por
feature y mes, métricas e intervalos.

## 3. Puesta en marcha en AWS, en orden

1. **Bootstrap (local, con credenciales de administrador).** Agrega los
   permisos para crear la MLflow App y el repositorio de entrenamiento, y deja
   que el rol de push publique la imagen nueva.

   ```bash
   cd infrastructure/terraform/bootstrap
   terraform plan -out=training.tfplan   # 0 to add, ~3 to change: solo políticas
   terraform apply training.tfplan
   ```

2. **Fusionar el PR y ejecutar *Terraform development deploy*.** El plan debe
   mostrar el repositorio ECR de entrenamiento y su política, el grupo de logs
   `/aws/sagemaker/TrainingJobs`, dos roles con sus políticas y la
   `aws_sagemaker_mlflow_app`. La app tarda 2 a 3 minutos en crearse.
   Si el grupo de logs ya existe porque alguna vez corrió un training job en la
   cuenta, importarlo antes:
   `terraform import aws_cloudwatch_log_group.training_jobs /aws/sagemaker/TrainingJobs`.

3. **Publicar la imagen de entrenamiento.** El workflow *Publish training
   image* corre al fusionar. Si lo hizo antes de que existiera el repositorio,
   lanzarlo de nuevo a mano. El digest aparece en el resumen del job.

4. **Subir el dataset:**

   ```bash
   BUCKET=$(terraform -chdir=infrastructure/terraform/environments/dev output -raw data_bucket_name)
   aws s3 cp data-science/data/modeling_dataset.parquet \
     s3://$BUCKET/datasets/modeling/pkdd99-berka-sha256-75ab2f39/modeling_dataset.parquet --sse AES256
   ```

5. **Lanzar la simulación en SageMaker:**

   ```bash
   cd infrastructure/terraform/environments/dev
   IMAGE="$(terraform output -raw training_repository_url)@<digest del paso 3>"
   ROLE=$(terraform output -raw sagemaker_training_role_arn)
   MLFLOW=$(terraform output -raw mlflow_app_arn)
   cd -
   python mlops/sagemaker/start_training_job.py --image "$IMAGE" --role-arn "$ROLE" \
     --bucket "$BUCKET" --mlflow-app-arn "$MLFLOW" --mode retraining-simulation --wait
   ```

   La consola muestra el job en *Training → Training jobs*, con sus logs en
   CloudWatch. Con `--spot` cuesta menos, pero puede esperar capacidad.

6. **Entrenar un candidato** con otros cortes:

   ```bash
   python mlops/sagemaker/start_training_job.py --image "$IMAGE" --role-arn "$ROLE" \
     --bucket "$BUCKET" --mlflow-app-arn "$MLFLOW" --mode train \
     --hyperparameter train_end=1996-06-30 --hyperparameter validation_start=1996-07-31 \
     --hyperparameter validation_end=1997-06-30 --wait
   ```

   Al terminar, el comando imprime `model_artifact_key`
   (`models/training-jobs/<job>/output/model.tar.gz`).

## 4. Ver MLflow

- **Consola:** en SageMaker AI, la sección de MLflow lista la app
  `credit-risk-mlops-development` con el enlace para abrir la UI. La ubicación
  del menú cambia entre versiones de la consola.
- **CLI** (una URL temporal):

  ```bash
  aws sagemaker create-presigned-mlflow-app-url --arn "$MLFLOW" --query AuthorizedUrl --output text
  ```

- **Desde la laptop**, para que las corridas locales también lleguen a la app:

  ```bash
  pip install -e '.[aws]'   # sagemaker-mlflow y boto3
  MLFLOW_TRACKING_URI="$MLFLOW" PYTHONPATH=data-science/src:. python -m mlops.experiments.retraining
  ```

Qué hay en MLflow:

| Experimento | Corridas |
|---|---|
| `credit-risk-retraining-simulation` | Una corrida padre por simulación, con una hija por fecha de reentreno (métricas del campeón y del retador, Δ e intervalos, tag `verdict`). La padre tiene las series `drift_psi_max`, `drift_score_psi` y `psi_<feature>` con un paso por mes, que se ven como gráfico, y los artefactos `report.json` y `summary.md` |
| `credit-risk-candidates` | Un candidato por job `train`: parámetros, cortes, métricas de train, validación y test, y el modelo de MLflow con su firma |
| `credit-risk-baseline` | `modeling.py`, cuando se ejecuta con `MLFLOW_TRACKING_URI` |

Las corridas de un job llevan los tags `sagemaker.training_job_name`,
`sagemaker.training_job_arn`, `image_version` y `dataset_uri`.

## 5. Promover un candidato

El job no despliega nada. Para llevar un candidato al endpoint, seguir
ADR-0005: revisar sus métricas en MLflow contra el campeón en las mismas
cohortes, regenerar el perfil de referencia con ese modelo y cambiar
`model_artifact_key` en `serving-release.auto.tfvars.json` mediante un PR.
El rol del endpoint ya puede leer `models/training-jobs/`.

## 6. Costos

| Pieza | Costo |
|---|---|
| MLflow App | Sin cargo por hora; solo S3 de `mlflow/` (KB a MB) |
| Job `retraining-simulation` en `ml.m5.large` | ~3 a 5 min facturables, < USD 0.01 |
| Job `train` | ~2 a 4 min, < USD 0.01 |
| Imagen de entrenamiento en ECR | ~1 GB por versión, ~USD 0.10 al mes cada una |

No hay nada que apagar: el job termina solo y la app no cobra por hora.
