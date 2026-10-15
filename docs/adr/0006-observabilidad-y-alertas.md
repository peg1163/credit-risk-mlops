# ADR-0006: Observabilidad y alertas

- Estado: Propuesto
- Fecha: 2026-09-18
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

Se necesitan logs correlacionados, métricas operativas, calidad de datos, drift,
performance diferida y alertas. La frecuencia mensual y el presupuesto pequeño
desaconsejan una plataforma de observabilidad siempre activa.

## Opciones consideradas

### Opción A — CloudWatch + artefactos analíticos en S3

CloudWatch recibe logs, métricas y alarmas operativas; S3 guarda reportes
versionados de calidad y performance. Un dashboard pequeño presenta las señales
principales.

### Opción B — Stack dedicado Prometheus/Grafana

Ofrece flexibilidad, pero requiere servicios, almacenamiento y operación que no
se justifican para jobs mensuales.

### Opción C — Solo reportes en S3

Es barato y reproducible, pero no proporciona alarmas oportunas ni una vista
operativa suficiente.

## Recomendación técnica

Elegir **CloudWatch + S3**. Mantener logs con retención finita, métricas de baja
cardinalidad y reportes científicos completos en S3. El canal de notificación
se configurará sin exponer direcciones en el repositorio.

## Resolución del propietario

- Decisión: [ ] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida:
- Justificación:
- Condiciones o cambios solicitados:
- Fecha de decisión:

## Consecuencias si se acepta la recomendación

- No se opera un stack de monitoreo adicional.
- `batch_id` y run ID deben aparecer en cada log y métrica relevante.
- Los umbrales científicos siguen la política existente y no disparan promoción
  automática.
- Se deben controlar cardinalidad y retención para evitar costos inesperados.

## Validación y criterios de reversión

- Inyectar fallos de job, stale data y schema para probar alarmas.
- Confirmar que una alarma conduce al runbook correcto.
- Reevaluar si la cantidad de servicios, métricas o usuarios exige consultas y
  visualizaciones más avanzadas.
