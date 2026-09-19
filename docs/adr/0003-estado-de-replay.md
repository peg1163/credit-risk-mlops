# ADR-0003: Persistencia del estado de replay

- Estado: Aceptado
- Fecha: 2026-09-19
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

Replay debe rechazar periodos duplicados o anteriores, avanzar únicamente tras
una liberación válida y recuperarse de fallos. El handoff permite S3 versionado
o DynamoDB; la concurrencia esperada inicial es mínima.

## Opciones consideradas

### Opción A — Manifiesto de estado versionado en S3

Minimiza componentes y costo. Facilita auditoría y recuperación de versiones,
pero requiere diseñar cuidadosamente escritura condicional, idempotencia y
exclusión de ejecuciones concurrentes.

### Opción B — Tabla DynamoDB

Ofrece escrituras condicionales y coordinación concurrente robusta. Añade otro
servicio, schema y permisos, aunque su costo a esta escala sería pequeño.

## Recomendación técnica

Elegir **S3 versionado** para la primera versión, combinado con el control de
concurrencia del orquestador y manifiestos inmutables por `batch_id`. Migrar a
DynamoDB si se habilitan ejecuciones paralelas o múltiples productores.

## Resolución del propietario

- Decisión: [x] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida: Opción A — manifiestos y cursor de replay en S3 versionado.
- Justificación: existe un único pipeline mensual coordinado por Step Functions;
  S3 cubre el estado pequeño y secuencial sin incorporar otra base de datos.
- Condiciones o cambios solicitados: utilizar un `current.json` pequeño,
  manifiestos inmutables por periodo y registros de intento separados. Proteger
  las escrituras con `If-Match`/`If-None-Match`, checksums, claves deterministas
  e idempotencia. El cursor solo avanza después de verificar outputs y confirmar
  el manifiesto. Reevaluar DynamoDB si aparecen concurrencia real o múltiples
  productores.
- Fecha de decisión: 2026-09-19

## Consecuencias de la decisión

- No se crea una base de datos para un único cursor mensual.
- Debe existir una única ejecución activa y una comprobación antes de confirmar
  el nuevo cursor.
- La recuperación utiliza version IDs y queda documentada en un runbook.

## Validación y criterios de reversión

- Simular fallo antes y después de escribir outputs y comprobar el cursor.
- Lanzar dos ejecuciones con el mismo periodo y verificar que solo una confirma.
- Migrar a DynamoDB antes de permitir concurrencia que S3 no coordine con
  seguridad suficiente.
