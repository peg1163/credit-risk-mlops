# ADR-0005: Registro y promoción de modelos

- Estado: Propuesto
- Fecha: 2026-09-18
- Última revisión: 2026-11-15, para incluir la promoción en el endpoint de ADR-0008
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

### Promoción en el endpoint

El batch lee el puntero del campeón en cada ejecución, así que promover es
escribir un manifiesto nuevo. El endpoint de ADR-0008 no lee punteros:

- Un `SageMaker Model` fija la imagen, referenciada **por digest**, y el
  `model.tar.gz`. Un `EndpointConfig` fija ese modelo.
- Promover en el endpoint significa crear un modelo y una configuración nuevos
  y actualizar el endpoint. El rollback consiste en volver a la configuración
  anterior.
- El manifiesto de promoción registra el digest de la imagen, la versión S3 del
  `model.tar.gz` y el nombre de la configuración de endpoint, para que batch y
  endpoint promuevan y reviertan el mismo campeón.
- La política de ciclo de vida de ECR debe conservar las imágenes del campeón
  vigente y de los anteriores dentro de la ventana de rollback. Un rollback a
  una configuración cuya imagen ya no está en ECR no es un rollback válido.
  La convención de tags y la retención se definen en
  [ADR-0009](0009-tags-y-retencion-de-imagenes-ecr.md).
- Promover un campeón nuevo también exige regenerar
  `monitoring/reference/profile.json`, porque el drift se mide contra el split
  de entrenamiento del campeón vigente.

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
- Revertir el endpoint a la configuración anterior y comprobar que su imagen
  sigue disponible en ECR.
- Rechazar bundles incompletos, checksums inválidos o contratos incompatibles.
- Reevaluar cuando la gestión manual de metadatos deje de ser sostenible.
