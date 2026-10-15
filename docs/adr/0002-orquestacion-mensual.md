# ADR-0002: Orquestación mensual

- Estado: Aceptado
- Fecha: 2026-09-19
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

Replay, features, inferencia y validación se ejecutan en orden, con una rama de
warm-up que no genera predicciones. Cada paso necesita timeout, reintentos
selectivos, trazabilidad y alarma ante fallo.

## Opciones consideradas

### Opción A — EventBridge Scheduler y Step Functions Standard

Scheduler inicia una state machine mensual. Step Functions representa orden,
ramas, reintentos y estado observable sin un proceso coordinador permanente.

### Opción B — EventBridge Scheduler y un script coordinador

Reutiliza el shell actual dentro de un único job. Es simple al inicio, pero
reduce el aislamiento, la visibilidad por etapa y la reanudación segura.

### Opción C — Managed Workflows for Apache Airflow

Ofrece un orquestador general, pero su costo y operación son desproporcionados
para un único DAG mensual pequeño.

## Recomendación técnica

Elegir **EventBridge Scheduler + Step Functions Standard**. Modelar cada imagen
como etapa y conservar una ejecución manual parametrizada para backfills
aprobados.

## Resolución del propietario

- Decisión: [x] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida: Opción A — EventBridge Scheduler y Step Functions Standard.
- Justificación: separar el reloj mensual de la coordinación, conservar
  visibilidad por etapa y evitar implementar un orquestador propio o desplegar
  una plataforma Airflow completa.
- Condiciones o cambios solicitados: las tasks seguirán ejecutándose sobre ECS
  Fargate conforme a ADR-0001; los reintentos se limitarán a errores transitorios
  y todo inicio utilizará un `batch_id` idempotente.
- Fecha de decisión: 2026-09-19

## Consecuencias de la decisión

- El flujo y sus errores serán visibles por etapa.
- Habrá costo por transición, aunque bajo para una frecuencia mensual.
- Los reintentos solo cubrirán errores transitorios; controles de datos no se
  reintentarán automáticamente.
- El periodo y `batch_id` serán parámetros explícitos de la ejecución.

## Validación y criterios de reversión

- Probar éxito, warm-up, timeout, error transitorio y error permanente.
- Verificar que dos ejecuciones del mismo `batch_id` no dupliquen salidas.
- Reevaluar si se incorporan muchos DAG heterogéneos o dependencias complejas.
