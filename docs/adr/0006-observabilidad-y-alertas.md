# ADR-0006: Observabilidad y alertas

- Estado: Propuesto
- Fecha: 2026-09-18
- Última revisión: 2026-11-16, para reflejar la implementación del endpoint serverless de ADR-0008
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

Se necesitan logs correlacionados, métricas operativas, calidad de datos, drift,
performance diferida y alertas. El presupuesto pequeño desaconseja una
plataforma de observabilidad siempre activa.

Hay dos cargas con ritmos distintos:

- **Pipeline batch mensual** (ADR-0001 y ADR-0002): jobs que corren y terminan.
- **Endpoint serverless** (ADR-0008): solicitudes durante el día, con periodos
  sin tráfico y sin Data Capture.

SageMaker Model Monitor ya no está abierto a clientes nuevos, así que el cálculo
de drift y de performance es código del proyecto en cualquier caso.

## Opciones consideradas

### Opción A — CloudWatch + artefactos analíticos en S3

CloudWatch recibe logs, métricas y alarmas operativas; S3 guarda reportes
versionados de calidad y performance. Un dashboard pequeño presenta las señales
principales.

### Opción B — Stack dedicado Prometheus/Grafana

Ofrece flexibilidad, pero requiere servicios, almacenamiento y operación que no
se justifican para este volumen. Grafana no produce métricas: para SageMaker
las leería desde CloudWatch. La versión administrada cobra por usuario y la
propia necesita un servidor encendido.

### Opción C — Solo reportes en S3

Es barato y reproducible, pero no proporciona alarmas oportunas ni una vista
operativa suficiente.

## Recomendación técnica

Elegir **CloudWatch + S3**. Mantener logs con retención finita, métricas de baja
cardinalidad y reportes científicos completos en S3. El canal de notificación
se configurará sin exponer direcciones en el repositorio. Grafana puede usarse
en local, leyendo CloudWatch, solo como ejercicio de visualización; las alarmas
viven en CloudWatch.

El monitoreo se organiza en tres capas.

### Capa 1 — Disponibilidad

| Señal | Origen | Alarma inicial |
|---|---|---|
| El endpoint no responde | Lambda canary programada cada 5 a 15 minutos que invoca el endpoint con la solicitud de ejemplo y publica la métrica propia `CanaryOK` y su latencia | `CanaryOK` < 1 en 2 de 3 periodos; la falta de datos cuenta como falla |
| Errores del modelo | `Invocation5XXErrors` | suma > 0 en 5 minutos |
| Clientes con datos inválidos | `Invocation4XXErrors` | umbral a fijar tras observar tráfico real |
| Lentitud y arranques en frío | `ModelLatency`, `OverheadLatency` | p90 sobre un umbral a fijar tras observar valores reales |
| Endpoint fallido | evento de cambio de estado en EventBridge | cualquier paso a `Failed` |
| Job batch fallido | estado de la ejecución de Step Functions | cualquier ejecución fallida |

Sin tráfico no hay métricas de invocación; por eso el canary es obligatorio.
Sus solicitudes llevan una marca y se excluyen del drift.

### Capa 2 — Captura y tráfico

- Un metric filter sobre los logs de captura cuenta solo solicitudes reales.
- Alarma por tráfico anormalmente bajo, con umbral fijo al inicio y anomaly
  detection cuando haya historia suficiente.
- El job diario publica la **brecha de captura**: solicitudes según CloudWatch
  menos líneas guardadas en S3. Cualquier valor mayor que cero es crítico.

### Capa 3 — Calidad del modelo

Un job diario, programado con EventBridge Scheduler, lee la captura en S3,
la compara con un perfil de referencia del split de entrenamiento y publica
métricas propias en CloudWatch. El reporte completo se guarda en
`monitoring/endpoint/daily/` en S3.

El job es una Lambda sin dependencias externas: el PSI se calcula en Python
puro con los deciles del perfil de referencia. Evidently necesitaría una
imagen de Lambda propia y no aporta más al cálculo diario con unas 100
solicitudes; queda como opción para reportes completos fuera de línea.

| Métrica | Ventana | Umbral |
|---|---|---|
| Tasa de nulos y de rechazos | día | +5 puntos porcentuales sobre lo habitual |
| Score promedio y tasa de `decision = 1` | día | anomaly detection |
| PSI máximo por variable y PSI del score | móvil de 7 días | ≥ 0.10 investigar, ≥ 0.25 material |
| ROC-AUC, KS, Brier y recall | cohorte de hace seis meses | según `MONITORING_AND_RETRAINING.md` |

Las alarmas de drift van al tópico de aviso aunque el PSI sea material: abren
una investigación, no una respuesta inmediata. El PSI se publica solo con al
menos 30 registros reales en la ventana.

La evaluación retrospectiva une la captura con las etiquetas maduras por
`(account_id, observation_date)` y se ejecuta como script
(`mlops/monitoring/retrospective.py`) cuando madura una cohorte, porque
necesita las dependencias científicas y corre una vez por mes.

El PSI diario se calcula sobre una ventana móvil porque con unas 100 solicitudes
por día el valor de un solo día tiene demasiado ruido de muestreo.

### Notificación

- Tópico SNS **crítico**: canary, 5XX, endpoint fallido, job batch fallido,
  brecha de captura y fallo de la Lambda que copia la captura.
- Tópico SNS **aviso**: drift, tráfico bajo, 4XX, latencia, métricas del
  modelo y fallo del job de calidad.
- Un dashboard de CloudWatch con una fila por capa.

## Resolución del propietario

- Decisión: [ ] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida:
- Justificación:
- Condiciones o cambios solicitados:
- Fecha de decisión:

## Consecuencias si se acepta la recomendación

- No se opera un stack de monitoreo adicional.
- `batch_id` y run ID deben aparecer en cada log y métrica relevante del batch;
  el identificador de solicitud cumple ese papel en el endpoint.
- Los umbrales científicos siguen la política existente y no disparan promoción
  automática.
- Se deben controlar cardinalidad y retención para evitar costos inesperados.
- El costo del monitoreo puede superar al del endpoint serverless; se prefiere
  una Lambda programada sobre CloudWatch Synthetics para el canary.
- Batch y endpoint tienen capacidades de observabilidad distintas por
  limitaciones de la plataforma, no por diseño.

## Validación y criterios de reversión

- Inyectar fallos de job, stale data y schema para probar alarmas.
- Detener o romper el endpoint y comprobar que la alarma del canary dispara
  aunque no haya tráfico real.
- Eliminar una línea de captura y comprobar que la brecha de captura lo detecta.
- Confirmar que una alarma conduce al runbook correcto.
- Reevaluar si la cantidad de servicios, métricas o usuarios exige consultas y
  visualizaciones más avanzadas.

## Implementación

- Infraestructura: `infrastructure/terraform/environments/dev/monitoring.tf`
  y `dashboard.tf`.
- Código: `mlops/monitoring/` (`canary.py`, `capture_export.py`,
  `quality.py`, `build_reference_profile.py`, `retrospective.py`).
- Operación: [`SAGEMAKER_ENDPOINT_RUNBOOK.md`](../SAGEMAKER_ENDPOINT_RUNBOOK.md).

## Referencias

- [ADR-0008](0008-endpoint-serverless-con-captura-propia.md)
- [`MONITORING_AND_RETRAINING.md`](../MONITORING_AND_RETRAINING.md)
- [Cambio de disponibilidad de Model Monitor](https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor-availability-change.html)
