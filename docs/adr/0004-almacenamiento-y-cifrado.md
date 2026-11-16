# ADR-0004: Almacenamiento, aislamiento y cifrado

- Estado: Propuesto
- Fecha: 2026-09-18
- Última revisión: 2026-11-15, para incluir el endpoint de ADR-0008 y ECR
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

### Prefijos del endpoint y del monitoreo

ADR-0008 y ADR-0006 agregan dos prefijos al bucket de development:

| Prefijo | Escribe | Lee |
|---|---|---|
| `endpoint-capture/date=YYYY-MM-DD/capture.jsonl` | job diario de copia desde CloudWatch Logs | job de calidad y evaluación retrospectiva |
| `monitoring/reference/profile.json` | persona, al promover un campeón | job de calidad |
| `monitoring/endpoint/daily/date=YYYY-MM-DD/report.json` | job de calidad | personas y dashboards |

- El rol de ejecución del endpoint solo lee `models/`. No escribe en S3, porque
  la captura sale por CloudWatch Logs, y no lee `raw-archive/` ni `labels/`.
- Solo el job retrospectivo de monitoreo lee `labels/`.
- El grupo de logs del endpoint tiene retención finita, por ejemplo 30 días; la
  copia permanente de la captura vive en S3.
- La captura contiene las features de cada solicitud. La expiración de versiones
  no actuales aplica, pero la versión actual de cada día se conserva al menos
  hasta que madure su cohorte de etiquetas (seis meses) y se evalúe.

### Cifrado del registro de imágenes

Los repositorios ECR declaran cifrado **AES256 de forma explícita**, coherente
con SSE-S3. El tipo de cifrado de un repositorio ECR no se puede cambiar
después de crearlo; dejarlo al valor por omisión lo convierte en un descuido y
no en una decisión.

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
- Probar que el rol del endpoint no puede escribir en ningún prefijo de S3.
- Probar bloqueo público, TLS obligatorio, cifrado y versionado.
- Separar buckets o adoptar KMS si cambian sensibilidad, actores, cumplimiento
  o necesidad de revocación granular.
