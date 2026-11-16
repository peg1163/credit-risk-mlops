# Endpoint serverless: despliegue, promoción y monitoreo

Última revisión: 2026-11-16. Implementa ADR-0004, ADR-0005, ADR-0006, ADR-0008 y
ADR-0009. **Esos ADR están en estado Propuesto**: completar la resolución del
propietario antes de aplicar en AWS.

## 1. Qué se despliega

```text
cliente ──InvokeEndpoint──▶ endpoint serverless ──stdout──▶ CloudWatch Logs
                               (sagemaker_serve.py)              │
canary (cada 10 min) ──synthetic=canary──▶ │          00:15 UTC  ▼
                                           │      capture_export ──▶ s3://<bucket>/endpoint-capture/date=…/capture.jsonl
                                           │                        └─▶ métrica CaptureGap
                                           │      00:45 UTC
                                           └────  quality ──▶ s3://<bucket>/monitoring/endpoint/daily/date=…/report.json
                                                            └─▶ PsiMax, ScorePsi, NullRateDeltaMaxPp, RejectionRate, ScoreMean, DecisionRate
alarmas CloudWatch + evento EndpointFailed ──▶ SNS crítico / aviso ──▶ correo
```

| Archivo | Contenido |
|---|---|
| `infrastructure/terraform/environments/dev/ecr.tf` | Repositorio de la imagen de serving y su retención |
| `.../sagemaker.tf` | Rol de ejecución, Model, EndpointConfig, endpoint y grupo de logs |
| `.../monitoring.tf` | Lambdas, horarios, SNS, alarmas y evento de endpoint fallido |
| `.../dashboard.tf` | Dashboard con una fila por capa de ADR-0006 |
| `.../serving-release.auto.tfvars.json` | Digest de imagen y clave del modelo desplegados |
| `infrastructure/terraform/bootstrap/github_development_serving_permissions.tf` | Permisos de CI y rol de push a ECR |
| `mlops/monitoring/` | Código de las Lambdas, perfil de referencia y evaluación retrospectiva |
| `.github/workflows/publish-serving-image.yml` | Publica imágenes `v<semver>-<sha7>` desde `main` |

Mientras `serving-release.auto.tfvars.json` tenga `null`, Terraform solo crea
el repositorio ECR, el rol de ejecución, el grupo de logs y los tópicos SNS.
El endpoint y su monitoreo aparecen cuando se definen el digest y el modelo.

## 2. Despliegue inicial, en orden

Antes de empezar: cuenta y región correctas, presupuesto revisado y ADR
aceptados.

1. **Bootstrap (local, con credenciales de administrador).** Agrega los
   permisos de los roles de plan y apply y crea el rol de push a ECR.

   ```bash
   cd infrastructure/terraform/bootstrap
   terraform plan -out=serving.tfplan   # revisar: solo políticas y un rol nuevo
   terraform apply serving.tfplan
   terraform output -raw github_actions_ecr_push_development_role_arn
   ```

   Guardar ese ARN en la variable de GitHub `AWS_ECR_PUSH_ROLE_ARN` y, si se
   quieren correos, el secreto `ALERT_EMAIL`.

2. **Primer apply de development** con el workflow *Terraform development
   deploy*. Crea ECR, SNS, rol de ejecución y grupo de logs. Si hay correo,
   confirmar las dos suscripciones desde el mensaje de AWS.

3. **Publicar la imagen.** Al fusionar en `main` un cambio de
   `data-science/src/` o de `mlops/docker/sagemaker-inference.*`, el workflow
   *Publish serving image* sube `v<versión>-<sha7>` y deja el digest en el
   resumen del job. También se puede lanzar a mano. Para pruebas:

   ```bash
   mlops/scripts/push-serving-image-dev.sh <serving_repository_url>   # tag dev-<sha7>, expira en 7 días
   ```

4. **Subir el modelo** a una clave que no se reutilice:

   ```bash
   python mlops/sagemaker/package_model.py
   aws s3 cp dist/sagemaker/model.tar.gz \
     s3://<bucket>/models/version=0.1.0/model.tar.gz --sse AES256
   aws s3api head-object --bucket <bucket> \
     --key models/version=0.1.0/model.tar.gz --query VersionId   # registrar
   ```

5. **Subir el perfil de referencia** del campeón:

   ```bash
   PYTHONPATH=data-science/src:. python mlops/monitoring/build_reference_profile.py
   aws s3 cp dist/monitoring/profile.json \
     s3://<bucket>/monitoring/reference/profile.json --sse AES256
   ```

6. **Desplegar el endpoint.** En un PR, completar
   `serving-release.auto.tfvars.json` con el digest del paso 3 y la clave del
   paso 4. Al fusionar, ejecutar el workflow de deploy y revisar en el plan:
   un Model y un EndpointConfig con sufijo nuevo, el endpoint, 3 Lambdas,
   3 horarios, alarmas y dashboard.

7. **Probar:**

   ```bash
   aws sagemaker-runtime invoke-endpoint \
     --endpoint-name credit-risk-mlops-development-serving \
     --content-type application/json \
     --body fileb://dist/sagemaker/endpoint-example-1998-01.json /dev/stdout
   ```

   La primera llamada puede tardar por el arranque en frío. A los pocos
   minutos debe haber líneas `inference_capture` en
   `/aws/sagemaker/Endpoints/credit-risk-mlops-development-serving` y la
   métrica `CanaryOK` en 1. Para no esperar al día siguiente, invocar
   `capture_export` y `quality` con `{"date": "<hoy UTC>"}`.

## 3. Promoción y rollback (ADR-0005)

- **Imagen nueva:** subir `mlops/docker/sagemaker-inference.version` si cambia
  el comportamiento, fusionar, copiar el digest publicado a
  `serving-release.auto.tfvars.json` en otro PR y aplicar.
- **Modelo nuevo:** subirlo a una clave nueva bajo `models/`, regenerar y subir
  el perfil de referencia, cambiar `model_artifact_key` y aplicar.
- **Rollback:** revertir el commit de `serving-release.auto.tfvars.json` y
  aplicar. SageMaker vuelve a la configuración anterior; su imagen sigue en
  ECR porque el workflow de publicación se niega a subir una imagen que
  sacaría a la desplegada de las 10 conservadas.
- Registrar en el manifiesto de promoción el digest, la versión S3 del modelo
  y el output `endpoint_config_name`.

## 4. Qué hacer ante cada alarma

| Alarma | Tópico | Primer paso |
|---|---|---|
| `endpoint-canary-failed` | crítico | Estado del endpoint en SageMaker; logs del canary y del endpoint |
| `endpoint-5xx` | crítico | Buscar `"status":"error"` en el grupo de logs del endpoint |
| `endpoint-capture-gap` | crítico | Ver el resultado de `capture_export`; reejecutarlo con la fecha afectada antes de que venza la retención de logs |
| `capture-export-errors` | crítico | Igual que la anterior |
| `endpoint-failed` (EventBridge) | crítico | `FailureReason` en `describe-endpoint`; rollback si coincide con un despliegue |
| `endpoint-4xx`, `endpoint-rejection-rate` | aviso | Campo `error` de las líneas `rejected`: qué cliente envía qué |
| `endpoint-*-latency-p90` | aviso | `OverheadLatency` alto = arranques en frío; `ModelLatency` alto = modelo |
| `endpoint-null-rate` | aviso | `null_rate` en el reporte diario |
| `endpoint-psi-investigate`, `endpoint-psi-material`, `endpoint-score-psi` | aviso | `window.psi` del reporte; abre una investigación, no reentrena |
| `endpoint-scoremean-anomaly`, `endpoint-decisionrate-anomaly` | aviso | Útil tras unas dos semanas de historia |
| `quality-errors` | aviso | Suele faltar `profile.json` o la captura del día |

## 5. Evaluación retrospectiva

Cuando madura una cohorte (seis meses):

```bash
aws s3 sync s3://<bucket>/endpoint-capture/ dist/endpoint-capture/
PYTHONPATH=data-science/src:. python mlops/monitoring/retrospective.py \
  --capture-dir dist/endpoint-capture \
  --labels data-science/data/labels/labels.parquet
```

El reporte marca `investigate` según los umbrales de
[`MONITORING_AND_RETRAINING.md`](MONITORING_AND_RETRAINING.md); el recall
necesita dos cohortes por debajo del umbral.

## 6. Costos y limpieza

- El endpoint serverless cobra por cómputo y datos procesados. El canary suma
  144 invocaciones diarias y además lo mantiene caliente; espaciarlo con
  `canary_schedule` si el costo importa más que la detección.
- Las alarmas de CloudWatch cobran por alarma al mes; hay unas 15.
- Para apagar el endpoint sin perder la configuración, poner los dos valores
  de `serving-release.auto.tfvars.json` en `null` y aplicar. ECR, logs, SNS
  y la captura en S3 se conservan.

## 7. Límites conocidos

- La alarma de job batch fallido de ADR-0006 espera a que exista la
  orquestación en Step Functions.
- La alarma de tráfico bajo está apagada hasta fijar
  `min_daily_real_requests` con tráfico real.
- `production-1998-01.parquet` tiene `balance_change_3m` nulo en todas las
  filas, y el entrenamiento nunca lo tiene nulo. Enviar ese lote al endpoint
  dispara `endpoint-null-rate` y un PSI alto en esa variable. El monitor
  funciona bien: el problema está en el pipeline de features y conviene
  revisarlo en `data-science/`.
