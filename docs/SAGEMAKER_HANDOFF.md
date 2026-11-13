# SageMaker: paquete local y guía de despliegue

Última revisión: 2026-11-12. Esta guía describe el paquete preparado en el
repositorio y los pasos que el propietario realizará en AWS. **Ningún recurso de
SageMaker se crea con los scripts de esta guía.** El estado real de AWS debe
comprobarse con la cuenta correcta antes de desplegar.

## 1. Qué problema resuelve este modelo

En el cierre de cada mes, para una cuenta que **ya tiene préstamo** y todavía no
ha presentado saldo negativo, el modelo v0.1.0 estima si aparecerá el **primer
saldo negativo en alguna transacción de los seis meses siguientes**. El saldo
corresponde a la cuenta bancaria; no representa la deuda pendiente del préstamo.
Los datos de entrada se calculan exclusivamente hasta la fecha de observación.

Este modelo sirve para un laboratorio educativo de ranking y MLOps. No está
validado para decisiones crediticias reales ni para evaluar a alguien antes de
otorgarle un préstamo. El score no es una probabilidad calibrada de impago; el
umbral de decisión de 0.75 es demostrativo. Ver [Model Card](MODEL_CARD.md),
[diccionario de variables](DATA_DICTIONARY.md) y
[handoff científico](../DATA_SCIENCE_HANDOFF.md).

## 2. Qué está preparado y qué falta

| Elemento | Estado |
|---|---|
| Modelo campeón local `champion.joblib` | Entrenado; no se versiona en Git |
| Servidor SageMaker `GET /ping` y `POST /invocations` | Implementado y probado localmente |
| Imagen Docker `credit-risk-sagemaker:0.1.0` | Construida localmente; aún no está en ECR |
| `model.tar.gz` con manifiesto y SHA-256 | Generado localmente; aún no está en S3 |
| JSON Lines y manifiesto para enero de 1998 | Generados localmente; aún no están en S3 |
| Bucket, roles, ECR, SageMaker Model, batch job, endpoint y MLflow en AWS | A cargo del propietario; no creados por este paquete |
| Captura de respuestas del endpoint y monitoreo automático | Diseño pendiente de implementar en AWS |

La arquitectura ECS Fargate documentada en los ADR existentes sigue siendo otra
línea de trabajo. Este paquete permite ensayar **SageMaker Batch Transform y un
endpoint con el mismo modelo**; no reemplaza por sí solo la arquitectura aprobada.

## 3. Contrato único de inferencia

El endpoint recibe **un objeto JSON** con `Content-Type: application/json`.
Batch Transform recibe **un objeto por línea** con
`Content-Type: application/jsonlines`. Los dos usan los mismos campos:

- `account_id`: identificador entero no negativo de la cuenta.
- `observation_date`: último día del mes en formato `YYYY-MM-DD`.
- Las 17 variables de [DATA_DICTIONARY.md](DATA_DICTIONARY.md): datos del
  préstamo, saldos, movimientos de los últimos tres meses, pagos y datos de la
  cuenta.

Cada variable debe estar presente. Las numéricas pueden ser `null` cuando el
modelo entrenado las imputa; `district_id` debe ser entero y
`statement_frequency` una cadena no vacía. Se rechazan campos adicionales,
valores no finitos y fechas que no sean cierres de mes. No enviar `target`,
`event_date`, datos futuros ni información personal en el cuerpo.

La respuesta contiene `account_id`, `observation_date`, `score`, `decision`,
`model_version`, `dataset_id` y `feature_pipeline_version`. Batch devuelve una
línea de salida por línea de entrada. El endpoint devuelve un solo objeto.
Ambos ejecutan la misma función de scoring en
[`sagemaker_serve.py`](../data-science/src/credit_risk/sagemaker_serve.py).

**Importante:** el endpoint puede puntuar una cuenta nueva para el sistema solo
si se conocen estas variables en esa fecha. Una persona que aún solicita su
primer préstamo y no tiene cuenta ni movimientos requiere otro modelo.

## 4. Crear los archivos locales

Ejecutar desde la raíz del repositorio, con el entorno Python del proyecto
activo y el modelo local disponible:

```bash
python mlops/sagemaker/package_model.py
PYTHONPATH=data-science/src python mlops/sagemaker/prepare_batch.py \
  --input data-science/data/features/production-1998-01.parquet \
  --period 1998-01 \
  --output dist/sagemaker/features-1998-01.jsonl
docker build -f mlops/docker/sagemaker-inference.Dockerfile \
  -t credit-risk-sagemaker:0.1.0 .
```

Se obtienen:

```text
dist/sagemaker/model.tar.gz
dist/sagemaker/features-1998-01.jsonl
dist/sagemaker/features-1998-01.jsonl.manifest.json
dist/sagemaker/endpoint-example-1998-01.json
```

El lote histórico de ejemplo contiene **524 cuentas**. El manifiesto incluye
`period`, `batch_id`, filas, SHA-256 de la entrada, SHA-256 del modelo, dataset
y versiones. `model.tar.gz` contiene `champion.joblib` y `manifest.json`.
El servidor valida el checksum del modelo al iniciar. `dist/` está ignorado por
Git; no subir modelos ni datos históricos al repositorio público.

## 5. Probar el contenedor antes de AWS

Para reproducir localmente el montaje que SageMaker hace en `/opt/ml/model`:

```bash
mkdir -p dist/sagemaker/extracted
tar -xzf dist/sagemaker/model.tar.gz -C dist/sagemaker/extracted
docker run --rm -p 127.0.0.1:8080:8080 \
  -v "$PWD/dist/sagemaker/extracted:/opt/ml/model:ro" \
  credit-risk-sagemaker:0.1.0 serve
```

En otra terminal:

```bash
curl --fail http://127.0.0.1:8080/ping
curl --fail -H 'Content-Type: application/json' \
  --data-binary @dist/sagemaker/endpoint-example-1998-01.json \
  http://127.0.0.1:8080/invocations
curl --fail -H 'Content-Type: application/jsonlines' \
  --data-binary @dist/sagemaker/features-1998-01.jsonl \
  http://127.0.0.1:8080/invocations \
  -o dist/sagemaker/local-batch.out
```

`/ping` debe responder HTTP 200. La predicción individual de la cuenta 2 en el
archivo de ejemplo devuelve aproximadamente `0.1305304266`; las 524 líneas
del batch deben producir 524 líneas de salida. Las pruebas automatizadas
comparan el score de este servidor con el predictor Parquet existente.

## 6. Preparación en AWS, en orden

Esta parte la ejecuta el propietario. Antes de empezar, verificar la **cuenta y
región AWS correctas**, el estado real del stack `development`, créditos
aplicables y presupuesto. El último estado remoto no se considera confirmado
desde este repositorio. No reutilizar planes Terraform guardados de ejecuciones
antiguas; crear y revisar un plan nuevo.

1. **S3.** Crear o reutilizar un bucket privado con versionado, cifrado y acceso
   público bloqueado. Separar prefijos de modelo, features, predicciones,
   etiquetas y monitoreo. Registrar la versión S3 del objeto del modelo.
2. **ECR.** Crear un repositorio privado, etiquetar y subir la imagen. Registrar
   el **digest** de ECR, además de la etiqueta `0.1.0`; la etiqueta puede cambiar.
3. **IAM.** Crear un rol de ejecución para SageMaker que pueda descargar la
   imagen y leer `models/` y `features/`, escribir `predictions/` y emitir logs.
   Inferencia no debe leer datos futuros `raw-archive/` ni `labels/`.
4. **SageMaker Model.** Referenciar el digest ECR y el URI S3 de
   `model.tar.gz`. SageMaker extrae ese archivo en `/opt/ml/model`; el contenedor
   escucha en el puerto 8080 y responde a `/ping` y `/invocations`.
5. **Batch Transform.** Subir el JSON Lines y su manifiesto. Crear un job con
   los parámetros de la sección siguiente y revisar las salidas.
6. **Endpoint temporal.** Crear una configuración de endpoint y un endpoint
   desde el mismo SageMaker Model. Invocar con el JSON de ejemplo, comparar
   scores y **eliminar el endpoint** al terminar el ejercicio.

Estos recursos estables deben quedar descritos en Terraform si se incorporan a
la infraestructura del proyecto; los jobs mensuales se lanzan en tiempo de
ejecución. Revisar `plan` antes de cada `apply` y mantener un state separado del
bootstrap. La documentación de AWS explica el contrato de
[contenedores propios](https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-inference-code.html)
y de [Batch Transform](https://docs.aws.amazon.com/sagemaker/latest/dg/batch-transform.html).

### Rutas S3 propuestas

```text
models/version=0.1.0/model.tar.gz
features/period=1998-01/batch_id=<batch_id>/features.jsonl
features/period=1998-01/batch_id=<batch_id>/features.jsonl.manifest.json
predictions/period=1998-01/batch_id=<batch_id>/features.jsonl.out
endpoint-capture/period=1998-01/<request_id>.json
labels/period=1998-01/...
monitoring/period=1998-01/...
```

El `<batch_id>` sale del manifiesto generado. SageMaker añade `.out` al archivo
de salida de Batch Transform; la ruta concreta puede incluir subcarpetas
derivadas del prefijo de entrada. Verificar el objeto generado antes de fijar
una ruta exacta en un consumidor. El endpoint **no guarda automáticamente su
respuesta**: la aplicación que lo invoca debe escribir su propio registro de
auditoría en S3. No poner DNI, nombre ni otros datos personales en claves S3.

### Configuración inicial de Batch Transform

| Parámetro | Valor para este paquete |
|---|---|
| Modelo | SageMaker Model creado con imagen ECR y `model.tar.gz` |
| Entrada | URI S3 de `features.jsonl` |
| `ContentType` | `application/jsonlines` |
| `SplitType` | `Line` |
| `Accept` | `application/jsonlines` |
| `AssembleWith` | `Line` |
| Instancias y concurrencia | Comenzar con 1 y 1 para este lote pequeño |
| Salida | Prefijo S3 `predictions/period=.../batch_id=.../` |

Al comparar batch con endpoint usar el mismo archivo de modelo y digest de
imagen. Verificar 524 entradas y salidas, unicidad de `(account_id,
observation_date)`, score finito en `[0,1]`, versión y dataset correctos.

## 7. Monitoreo que se añadirá después del despliegue

El empaquetado no implementa todavía jobs de monitoreo. La siguiente etapa
propuesta es una ejecución por periodo que lea features, predicciones y,
**seis meses después**, etiquetas maduras. Debe registrar en MLflow `period`,
`batch_id`, versión S3 de entrada y modelo, digest ECR, Git SHA, conteos,
distribución de scores y un informe de calidad. Para resultados maduros, añadir
ROC-AUC, PR-AUC, KS, Brier, calibración y recall según
[la política actual](MONITORING_AND_RETRAINING.md). CloudWatch debe recibir
errores operativos y alarmas de jobs o endpoint.

MLflow conserva y compara métricas; un job aparte debe calcularlas. Los
umbrales de drift abren una investigación, no un reentrenamiento automático.
AWS ya no da acceso a SageMaker Model Monitor a clientes nuevos y recomienda
soluciones con MLflow, Evidently y CloudWatch para batch y endpoints:
[cambio de disponibilidad](https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor-availability-change.html).

## 8. Costos, limpieza y límites

- Batch Transform usa cómputo durante el job. Verificar que finalizó y revisar
  el costo real después de cada prueba.
- Un endpoint de tiempo real puede seguir cobrando mientras está desplegado.
  [Eliminarlo](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints-delete-resources.html)
  al terminar; guardar la configuración y el modelo no equivale a mantenerlo
  encendido.
- S3, ECR, logs y un tracking server MLflow también pueden generar cargos o
  conservar datos. Revisar estos recursos al limpiar el laboratorio.
- Los créditos AWS solo compensan cargos elegibles y pueden vencer. Un aviso de
  presupuesto no apaga automáticamente los recursos.
- El modelo histórico no es apto para clientes actuales ni para una decisión
  crediticia real. Para solicitudes previas al desembolso se necesita otro
  objetivo y otro conjunto de datos.

## 9. Criterio de cierre de esta entrega local

- El archivo `model.tar.gz` contiene modelo y manifiesto con checksum válido.
- El lote JSON Lines y su manifiesto incluyen un periodo único y 524 filas.
- El contenedor construido localmente carga el artefacto empaquetado.
- El endpoint local devuelve un score y el batch usa exactamente el mismo
  contrato; los scores coinciden con el predictor existente.
- La suite de pruebas del repositorio y `git diff --check` pasan.

Estos criterios se comprobaron localmente el 2026-11-12. El despliegue, el
monitoreo automático y la validación de costos en AWS siguen pendientes.
