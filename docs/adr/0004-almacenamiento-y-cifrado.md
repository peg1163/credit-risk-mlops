# ADR-0004: Almacenamiento, aislamiento y cifrado

- Estado: Propuesto
- Fecha: 2026-09-18
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

La plataforma necesita datos raw, incoming, features, predictions, labels,
models y manifests. Raw y labels requieren aislamiento respecto de inferencia.
Terraform ya define un bucket versionado de development con SSE-S3, bloqueo
público, TLS obligatorio y expiración de versiones no actuales a 30 días.

## Opciones consideradas

### Opción A — Un bucket por entorno y separación por prefijos IAM

Reduce recursos y simplifica el laboratorio. El aislamiento depende de políticas
por prefijo bien probadas y una política de retención común o por reglas.

### Opción B — Buckets separados por zona de confianza

Separa físicamente raw/labels de outputs de inferencia y permite políticas de
retención y claves distintas. Aumenta recursos, policies y administración.

### Cifrado — SSE-S3 o SSE-KMS

SSE-S3 ofrece cifrado administrado sin una clave propia ni costo de llamadas
KMS. SSE-KMS permite controles y auditoría de clave más granulares a cambio de
costo y complejidad.

## Recomendación técnica

Para **development**, usar un bucket versionado con prefijos IAM y **SSE-S3**,
acompañado de tests negativos de acceso. Antes de production, reevaluar buckets
separados y SSE-KMS según sensibilidad, cumplimiento y amenaza real.

## Resolución del propietario

- Decisión: [ ] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida:
- Justificación:
- Condiciones o cambios solicitados:
- Fecha de decisión:

## Consecuencias si se acepta la recomendación

- Menor costo y superficie Terraform en development.
- Un error de policy podría romper el aislamiento; los tests de permisos son un
  criterio obligatorio, no opcional.
- La expiración nunca debe eliminar la única versión reproducible de un modelo,
  manifiesto o evidencia aprobada.

## Validación y criterios de reversión

- Probar que inferencia no puede leer `raw-archive/` ni `labels/`.
- Probar bloqueo público, TLS obligatorio, cifrado y versionado.
- Separar buckets o adoptar KMS si cambian sensibilidad, actores, cumplimiento
  o necesidad de revocación granular.
