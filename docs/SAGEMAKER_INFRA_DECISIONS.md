# Notas de diseño: infraestructura SageMaker y ECR

Última revisión: 2026-11-13

Este documento recoge el diseño discutido para llevar el modelo a SageMaker.
Son **notas de trabajo, no decisiones formales**: las decisiones vinculantes
viven en los ADR de `docs/adr/`. Varias de estas notas contradicen o amplían
ADR vigentes y están marcadas como tales.

No contiene identificadores de cuenta, nombres de bucket, ARN de roles ni
estado de Terraform.

## 1. Estado actual

Aplicado en AWS:

- Bucket de estado remoto con versionado, cifrado y bloqueo nativo.
- Proveedor OIDC de GitHub y tres roles: verificación de identidad, plan y
  apply de development.
- Bucket de datos de development con versionado, SSE-S3, bloqueo público,
  TLS obligatorio y reglas de ciclo de vida.

En progreso: `infrastructure/terraform/environments/dev/ecr.tf`.

Sin construir: todo SageMaker, MLflow en la nube, orquestación y alertas.

## 2. Repositorios ECR

### Un repositorio por imagen

Decisión propuesta: un repositorio por imagen, declarados con `for_each` sobre
un map. Razones, en orden de peso:

1. **IAM tiene granularidad de repositorio.** El execution role de SageMaker
   debe poder hacer pull de la imagen de runtime y de ninguna otra. Con un
   repositorio compartido eso es imposible.
2. **Las políticas de ciclo de vida divergen.** La imagen de runtime tiene
   EndpointConfig apuntándole y necesita retención conservadora; features y
   replay son desechables.
3. **El espacio de tags queda limpio**, un linaje de versión por componente.
4. **ECR no cobra por repositorio**, solo por almacenamiento y transferencia.

El map permite dar a cada imagen su propia retención sin duplicar recursos.
Agregar una imagen más adelante es agregar una clave.

### Inventario de imágenes

`mlops/docker/` tiene cuatro Dockerfiles y falta una quinta imagen:

| Dockerfile | Entrypoint | Destino en AWS |
|---|---|---|
| `features` | `build_features.py` | Processing job |
| `inference` | `predict.py` | Processing job (scoring batch) |
| `replay` | `replay.py` | pendiente de decidir si corre en AWS |
| `sagemaker-inference` | `credit_risk.sagemaker_serve`, puerto 8080 | endpoint |
| falta `train` | `train.py` existe sin Dockerfile | Training job |

El CI construye tres de ellas (`features`, `inference`, `replay`) y **no
construye `sagemaker-inference`**, que es la única que implementa el contrato
de serving. Tampoco existe ningún job que suba imágenes a ECR.

### Lo que dicen los requirements

Los archivos de dependencias ya dibujan el límite correcto entre imágenes:

- `requirements-inference.txt` y el camino de serving usan **exactamente las
  mismas dependencias**. Consolidar batch y serving en una sola imagen de
  runtime con dos entrypoints no cuesta tamaño adicional, y hace estructural
  la garantía de que ambos corren el mismo código.
- `mlflow` solo aparece en `requirements.txt`, que es el de entrenamiento.
  Mantener training como imagen aparte evita arrastrar ese árbol de
  dependencias al runtime y acorta el cold start del endpoint.
- `requirements-features.txt` y `requirements-replay.txt` son idénticos entre
  sí; hay una consolidación posible ahí.
- `pytest` está en el requirements de entrenamiento; debería moverse a un
  requirements de desarrollo.

### Decisiones irreversibles antes del primer apply

Dos argumentos de `aws_ecr_repository` fuerzan reemplazo del recurso, y con
`prevent_destroy = true` un reemplazo falla con error en vez de recrear:

- **`encryption_configuration`.** El tipo de cifrado de un repositorio ECR es
  inmutable. Si no se declara, AWS aplica AES256 por omisión y queda como
  descuido en vez de decisión. El ADR-0004 ya recomienda SSE-S3 para
  development, así que corresponde declararlo explícitamente.
- **`name`.** Cerrar el set de imágenes y la convención de nombres antes del
  primer apply.

Hacer el cambio a `for_each` antes del primer apply también evita tener que
usar bloques `moved` o cirugía de state más adelante.

### Convención de tags, sin cerrar

`image_tag_mutability = "IMMUTABLE"` implica que un tag no se puede reescribir,
así que semver puro falla cuando hay que reconstruir una misma versión, y
`latest` no es viable. El tag tiene tres consumidores y los tres mandan:

1. la persona que lee la consola de ECR;
2. el filtro de la política de ciclo de vida;
3. el `SageMaker Model`, que **fija el URI con tag de forma permanente**.

Opciones en discusión: semver con bump obligatorio, SHA de commit, o compuesto
`version-sha`. No decidido.

### Errores conocidos en `ecr.tf`

Commiteados a propósito como trabajo en progreso:

- `rulePriority` y `countNumber` están como string; la API espera enteros.
- `tagStatus = "tagged"` requiere `tagPrefixList` o `tagPatternList`.
- Falta la regla de `untagged`, que es la de menor riesgo.
- Falta `encryption_configuration`.
- Falta correr `terraform fmt`.
- El nombre local `data_lake` no corresponde a un repositorio de imágenes.

Ni `validate` ni `plan` detectan estos errores: el provider pasa el JSON tal
cual y AWS lo rechaza en el `apply`.

### Permisos pendientes en bootstrap

Una búsqueda de `ecr` sobre `infrastructure/terraform/bootstrap/` no devuelve
nada. Hacen falta dos conjuntos de permisos distintos y no deberían vivir en el
mismo rol:

- el rol de Terraform necesita **administrar** repositorios;
- el job de push del CI necesita **escribir imágenes**.

Falta también un output con la URL del repositorio para construir el image URI.

## 3. Contratos de contenedor de SageMaker

Son tres contratos distintos y los Dockerfiles actuales solo cumplen el de
serving:

| Runtime | Rutas | Invocación |
|---|---|---|
| Training | `/opt/ml/input/data/<canal>`, `/opt/ml/model` | argumento `train` |
| Processing | `/opt/ml/processing/input`, `/opt/ml/processing/output` | sin argumento |
| Serving | `/opt/ml/model` ya extraído, puerto 8080 | argumento `serve` |

**Bloqueo conocido:** `common.py` fija `ARTIFACTS` relativo al repositorio. En
un Training job solo sobreviven `/opt/ml/model` y `/opt/ml/output`; todo lo
demás se destruye con el contenedor. Hoy el job reportaría éxito y no dejaría
ni `champion.joblib` ni `metrics.json` ni `mlruns`. Es un cambio en
`data-science/`, no en Terraform ni en el Dockerfile.

`train.py` es un shim que llama a `modeling.main()`, que ignora `sys.argv`, así
que el argumento `train` no lo rompe.

Alternativa no descartada: los contenedores administrados de framework
(script mode) evitarían escribir `train.Dockerfile`, a costa de perder control
del digest de la imagen base, que `DATA_SCIENCE_HANDOFF.md` pide explícitamente.

## 4. Batch y endpoint

### Processing en vez de Batch Transform para producción

Batch Transform usa el contenedor de serving y haría estructural la paridad
entre batch y endpoint, pero es **orientado a registro**: no puede calcular
nada que cruce filas. `predict.py` sí lo hace (SHA-256 de la entrada completa,
conteo de filas, unicidad de llaves, manifiesto de corrida), y el ADR-0003
depende de ese manifiesto. Por eso el camino de producción es un Processing
job.

### Batch Transform como arnés de paridad

Propuesta: usar Batch Transform no como camino de producción sino como arnés
de verificación de paridad. Correrlo sobre el mismo fixture con el mismo
`model.tar.gz` y comparar contra la salida del Processing job da un registro
auditable en S3, es más barato y más reproducible que invocar el endpoint en
un bucle, y se apaga solo. Definir la tolerancia numérica a propósito: el
endpoint serializa a JSON y el batch escribe a archivo.

### Endpoint serverless y sus exclusiones

Propuesta: Serverless Inference en vez de un endpoint provisionado, porque el
endpoint existe para validación y paridad, no para tráfico de producción. No
cobra idle, así que puede quedarse arriba en vez de crearse y destruirse.

La documentación de AWS lista exclusiones que **afectan directamente al
ADR-0006**:

- sin **data capture**;
- sin **Model Monitor**;
- sin configuración de VPC ni aislamiento de red;
- sin endpoints multi-modelo, GPU, múltiples variantes de producción ni
  pipelines de inferencia.

Otros límites relevantes: memoria en escalones de 1024 a 6144 MB, concurrencia
máxima de 200 por endpoint, imagen de contenedor hasta 10 GB, 5 GB de disco
efímero. AWS recomienda **un solo worker y una sola copia del modelo** en el
contenedor, a diferencia de real-time; conviene revisar qué hace
`sagemaker_serve.py`. La métrica `OverheadLatency` de CloudWatch mide el cold
start.

**Puerta de un solo sentido:** un endpoint real-time no se puede convertir en
serverless, y un serverless convertido a real-time no se puede revertir.

Referencia: https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html

### Asimetría de promoción

El batch lee el puntero del campeón en cada corrida, así que promover es
escribir un manifiesto nuevo. El endpoint no lee punteros: un `SageMaker Model`
fija imagen y artefacto, y el `EndpointConfig` fija el model. Cambiar de modelo
exige una config nueva y un update del endpoint.

Consecuencia para ECR: los EndpointConfig anteriores retienen referencias duras
a imágenes viejas. El número de retención de la política de ciclo de vida tiene
que cubrir la ventana de rollback del ADR-0005.

## 5. MLflow

MLflow ya se usa como **librería cliente** (`mlflow==3.5.1` en
`requirements.txt`, `modeling.py` escribe a un `mlruns` local con un URI
`file://`). En esa forma no necesita ningún repositorio ECR.

Tres caminos para la nube y solo uno necesita imagen:

| Camino | Imagen en ECR |
|---|---|
| Archivos locales subidos a S3 | no |
| Tracking server administrado por SageMaker | no, AWS corre el contenedor |
| Auto-hospedado en Fargate o App Runner con RDS | sí, más RDS |

Dato técnico que cierra una idea intermedia: **el backend store de MLflow no
acepta S3**. Solo acepta un path de archivos, una URI de base de datos o HTTP
contra un tracking server. S3 sirve únicamente como artifact store. Por eso el
ADR-0005 terminó en S3 más manifiesto y no en MLflow.

**Conflicto con el ADR-0005:** ese ADR descartó la opción de MLflow
Tracking/Registry administrado por presupuesto y dejó escrito que no hay
servidor ni base de datos permanentes. El tracking server administrado también
factura por hora. Si se adopta, corresponde **reemplazar el ADR-0005 con un ADR
nuevo**, no contradecirlo en silencio. Además el ADR-0005 sigue en estado
Propuesto con la resolución del propietario en blanco.

Si el entrenamiento se mueve a SageMaker, el `mlruns` local deja de servir
porque vive en un contenedor efímero.

## 6. Monitoreo continuo

La política científica ya está en `MONITORING_AND_RETRAINING.md`. Lo que sigue
es el diseño de ingeniería.

### Cadencia

Separar dos cosas que suelen mezclarse:

- **Controles de calidad de datos** (esquema, tipos, duplicados, nulos,
  categorías desconocidas) pueden correr por cada llegada. Son deterministas.
- **Estadísticos de distribución** (PSI, distribución de scores) necesitan una
  cohorte. La cadencia de monitoreo sigue a la de scoring, no a la de llegada
  de datos.

### Los dos relojes

`label_horizon_months: 6` implica que la cohorte puntuada hoy no se puede
evaluar hasta dentro de seis meses. Hacen falta dos jobs distintos:

1. **Adelantado**, después de cada scoring: PSI, distribución de scores, tasa
   de decisión. Sin etiquetas.
2. **Retrospectivo**, sobre la cohorte de hace seis meses: ROC-AUC, PR-AUC, KS,
   Brier, calibración. Requiere releer predicciones viejas y cruzarlas con
   etiquetas nuevas.

Esto exige que las predicciones sean releíbles seis meses después con llaves
suficientes para el join, que es justo lo que da el manifiesto con `batch_id`.
`replay.py` y el ADR-0003 son la infraestructura del segundo reloj.

### Model Monitor no encaja

Los umbrales de `MONITORING_AND_RETRAINING.md` (PSI 0.10 y 0.25, ROC-AUC 0.75,
KS 0.30, deterioro de Brier de 25% contra la referencia 0.0449) no son
expresables en Model Monitor, que calcula sus propias estadísticas. Sumado a
que serverless no lo soporta y a que el scoring es Processing y no Batch
Transform, la recomendación es un **Processing job propio** que escriba el
reporte a `monitoring/` y emita métricas personalizadas a CloudWatch, con
alarmas que notifiquen por SNS.

### Dos trampas

- **El baseline va versionado con el modelo.** El PSI contra train solo tiene
  sentido comparando contra la distribución de entrenamiento de ese modelo.
  Promover un campeón promueve su baseline.
- **PSI sobre unas 524 cuentas tiene ruido de muestreo real.** Antes de confiar
  en el umbral de 0.10, hacer un bootstrap de la cohorte de entrenamiento
  contra sí misma para medir el piso de ruido propio. Monitorear por segmento
  desde el principio: el agregado puede estar plano mientras un segmento se
  degrada.

### Ventaja del dataset histórico

Con `replay_start` en 1997-10-31 y `production_start` en 1998-01-31, el sistema
de monitoreo se puede **validar contra historia conocida** antes de confiar en
él: verificar si los umbrales habrían disparado cuando debían y se habrían
quedado callados cuando no.

## 7. Preguntas abiertas

- Qué imágenes corren en AWS; `replay` sigue sin decidirse.
- Una imagen de runtime con dos entrypoints, o separadas.
- Imagen propia de training o script mode.
- Convención de tags para las imágenes que suben a ECR.
- Si se acepta el endpoint sin data capture ni Model Monitor, o se usa
  real-time.
- Número de retención de la política de ciclo de vida, atado a la ventana de
  rollback del ADR-0005.
- Resolución del propietario en el ADR-0005, hoy en blanco.

## 8. ADR que habría que tocar

- **ADR-0004**: declarar el cifrado de ECR explícitamente, no por omisión.
- **ADR-0005**: resolución en blanco; además, adoptar MLflow administrado
  exigiría reemplazarlo.
- **ADR-0006**: registrar que batch y endpoint tienen capacidades de
  observabilidad asimétricas por limitación de la plataforma, no por diseño.
