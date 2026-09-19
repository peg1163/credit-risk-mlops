# ADR-0005: Registro y promoción de modelos

- Estado: Propuesto
- Fecha: 2026-09-18
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

MLflow local conserva experimentos científicos, pero la ejecución cloud necesita
resolver un campeón inmutable y promover o revertir juntos modelo, threshold,
contrato de features e imagen. Mantener un servidor MLflow siempre activo no se
ajusta al presupuesto inicial.

## Opciones consideradas

### Opción A — Registro ligero en S3 y manifiesto versionado

Almacena bundle, checksum, métricas, model card, firma y un manifiesto de
promoción aprobado. No requiere servicio activo, pero la interfaz y validaciones
de promoción deben implementarse en CI/CD.

### Opción B — MLflow Tracking/Registry administrado por el proyecto

Ofrece UI y semántica de registro conocidas. Requiere backend, artefactos,
autenticación, disponibilidad y mantenimiento.

### Opción C — Servicio administrado de registro de modelos

Reduce operación del registry, pero acopla el flujo a un servicio adicional y
puede exceder las necesidades y el presupuesto de esta etapa.

## Recomendación técnica

Usar **S3 + manifiesto de promoción inmutable** en development. Conservar MLflow
local para experimentación y evaluar un registry administrado cuando existan
múltiples modelos, usuarios o promociones frecuentes.

## Resolución del propietario

- Decisión: [ ] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida:
- Justificación:
- Condiciones o cambios solicitados:
- Fecha de decisión:

## Consecuencias si se acepta la recomendación

- No hay servidor ni base de datos permanentes.
- La promoción debe validar checksums y compatibilidad antes de actualizar el
  puntero versionado del campeón.
- La evidencia de aprobación y rollback forma parte del manifiesto.

## Validación y criterios de reversión

- Promover un challenger de prueba y volver al campeón anterior sin ambigüedad.
- Rechazar bundles incompletos, checksums inválidos o contratos incompatibles.
- Reevaluar cuando la gestión manual de metadatos deje de ser sostenible.
