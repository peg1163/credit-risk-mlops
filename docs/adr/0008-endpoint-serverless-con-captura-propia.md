# ADR-0008: Endpoint de inferencia en línea serverless con captura propia

- Estado: Propuesto
- Fecha: 2026-11-15
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

Además del pipeline batch mensual, el proyecto quiere exponer el modelo v0.1.0
como un endpoint de SageMaker que reciba solicitudes durante el día. El volumen
esperado es bajo, del orden de 100 solicitudes diarias, con periodos sin tráfico.

Toda solicitud y su respuesta deben quedar guardadas para calcular calidad de
datos y drift, y para unir cada predicción con su etiqueta seis meses después.
La disponibilidad del endpoint también debe vigilarse.

Hechos verificados en la documentación de AWS el 2026-11-15:

- SageMaker Model Monitor ya no está abierto a clientes nuevos. AWS recomienda
  reemplazarlo con Evidently, MLflow, CloudWatch y SNS.
- Serverless Inference no soporta, entre otros, data capture, Model Monitor,
  configuración de VPC, aislamiento de red ni múltiples variantes de producción.
- Un endpoint real-time con instancia no se puede convertir en serverless. Un
  serverless se puede convertir en real-time, pero no se puede revertir.
- Serverless escala a cero sin tráfico y puede sufrir arranques en frío,
  medibles con la métrica `OverheadLatency`.
- AWS recomienda un solo worker y una sola copia del modelo por contenedor
  serverless.

Este ADR no cambia el runtime del pipeline batch. Replay, features e inferencia
mensual siguen sobre ECS Fargate según ADR-0001 y ADR-0002.

## Drivers de decisión

- Costo proporcional al uso: con unas 100 solicitudes diarias, una instancia
  encendida 24/7 cuesta cientos de veces más que el cómputo realmente usado.
- Captura completa de entradas y salidas, sin depender de que cada cliente la
  implemente.
- Detectar caídas del endpoint aunque no haya tráfico real.
- Usar el mismo contenedor y contrato que Batch Transform.

## Opciones consideradas

### Opción A — Endpoint real-time con instancia y Data Capture

Data Capture guarda solicitudes y respuestas en S3 sin código propio, y la
instancia no tiene arranques en frío. Cobra por hora aunque no haya tráfico:
referencia de terceros para `ml.t2.medium` en us-east-1, unos USD 0.056 por hora
(cerca de USD 40 al mes). Data Capture deja de capturar cuando el disco de la
instancia se llena, así que también requiere vigilar `DiskUtilization`.

### Opción B — Endpoint serverless con captura dentro del contenedor

`sagemaker_serve.py` escribe una línea JSON por solicitud en stdout. SageMaker
envía stdout a CloudWatch Logs y un job diario copia esas líneas a S3. Cobra
por milisegundo de cómputo y por datos procesados: menos de un centavo diario
para el volumen esperado. Cambia la imagen del endpoint y tiene arranques en
frío.

### Opción C — Endpoint serverless con captura en la aplicación cliente

El endpoint no cambia: cada cliente guarda su solicitud y la respuesta. Si un
cliente olvida hacerlo, faltan datos en el monitoreo, y la captura queda fuera
del control de este proyecto.

### Opción D — Sin endpoint, solo batch mensual

No requiere infraestructura en línea. No permite puntuar cuentas a demanda
durante el mes.

## Recomendación técnica

Elegir la **Opción B**. Detalle de la captura:

- Una línea por registro puntuado con identificador de solicitud, hora UTC,
  entrada completa, salida, `model_version`, versión de la imagen y estado. Un
  cuerpo JSON Lines produce una línea por registro con el mismo identificador,
  para no superar el tamaño máximo de un evento de CloudWatch Logs.
- El canary envía `CustomAttributes: synthetic=canary`; SageMaker reenvía ese
  valor al contenedor sin cambios y la línea queda marcada `synthetic: true`.
- El contenedor devuelve `request_id=<id>` en `CustomAttributes` para que el
  cliente pueda correlacionar su solicitud con la captura.
- Las solicitudes rechazadas (HTTP 400) y fallidas (HTTP 500) también se
  registran, sin su cuerpo, para medir la tasa de rechazo.
- La variable de entorno `CAPTURE_ENABLED=false` desactiva la captura, por
  ejemplo en Batch Transform, cuyos logs no forman parte de este flujo.
- Escribir en stdout y no directo a S3, para no agregar latencia ni un punto de
  falla dentro de la respuesta.
- El rol de ejecución del endpoint no necesita escribir en S3. El job diario
  copia los logs a `endpoint-capture/` (ver ADR-0004).
- El cuerpo nunca incluye nombre, DNI ni otros datos personales; el contrato ya
  los excluye.

La observabilidad del endpoint se define en ADR-0006.

## Resolución del propietario

- Decisión: [ ] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida:
- Justificación:
- Condiciones o cambios solicitados:
- Fecha de decisión:

## Consecuencias si se acepta la recomendación

### Positivas

- El costo del endpoint sigue al tráfico real y es casi nulo sin uso.
- La captura no depende de los clientes y cubre también las solicitudes
  rechazadas.
- El mismo contenedor sirve para el endpoint y para Batch Transform.

### Negativas y compromisos

- El contenedor cambia: la captura forma parte de una nueva versión de imagen
  (por ejemplo `0.2.0`), porque los tags de ECR son inmutables.
- No hay Data Capture ni Model Monitor: la captura y el análisis son código del
  proyecto.
- Los arranques en frío alargan algunas respuestas. Si una aplicación necesitara
  latencia baja garantizada, habría que evaluar Provisioned Concurrency o
  real-time.
- Pasar a real-time más adelante es posible, pero no se puede volver a
  serverless sobre el mismo endpoint.
- La retención de CloudWatch Logs debe ser finita y la copia permanente vive en
  S3; si el job de copia falla más días que la retención, se pierden datos.

## Validación y criterios de reversión

- Durante siete días seguidos, la brecha entre `Invocations` de CloudWatch y las
  líneas guardadas en S3 debe ser cero, descontando el canary.
- El score de una solicitud al endpoint coincide con el de la misma fila en
  Batch Transform, con la misma imagen y el mismo `model.tar.gz`.
- Revisar la decisión si el tráfico crece al punto de que una instancia cueste
  menos, o si los arranques en frío incumplen la latencia que exija un cliente.

## Implementación

- Captura: `data-science/src/credit_risk/sagemaker_serve.py`.
- Endpoint: `infrastructure/terraform/environments/dev/sagemaker.tf`.
- Imagen y retención: [ADR-0009](0009-tags-y-retencion-de-imagenes-ecr.md).

## Referencias

- [Serverless Inference: exclusiones y conversión](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html)
- [Cambio de disponibilidad de Model Monitor](https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor-availability-change.html)
- [SageMaker AI Pricing](https://aws.amazon.com/sagemaker/ai/pricing/)
- [`SAGEMAKER_HANDOFF.md`](../SAGEMAKER_HANDOFF.md)
- [`MONITORING_AND_RETRAINING.md`](../MONITORING_AND_RETRAINING.md)
