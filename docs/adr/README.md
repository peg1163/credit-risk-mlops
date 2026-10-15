# Architecture Decision Records

Este directorio contiene las decisiones de arquitectura del proyecto. Un ADR
describe una decisión, sus alternativas y consecuencias; no sustituye el código
ni una guía operativa.

## Flujo de aprobación

1. El autor prepara el contexto, opciones y recomendación.
2. El propietario completa la sección **Resolución del propietario**.
3. Cambia `Estado` a `Aceptado` o `Rechazado` y añade la fecha.
4. Si la decisión cambia después, se crea otro ADR que marque al anterior como
   `Reemplazado por ADR-NNNN`; no se reescribe la historia.
5. Solo un ADR `Aceptado` autoriza su implementación.

Estados permitidos: `Borrador`, `Propuesto`, `Aceptado`, `Rechazado`,
`Reemplazado` y `Obsoleto`.

## Índice

| ADR | Tema | Estado |
|---|---|---|
| [ADR-0001](0001-runtime-batch-administrado.md) | Runtime batch administrado | Aceptado |
| [ADR-0002](0002-orquestacion-mensual.md) | Orquestación mensual | Aceptado |
| [ADR-0003](0003-estado-de-replay.md) | Persistencia del estado de replay | Aceptado |
| [ADR-0004](0004-almacenamiento-y-cifrado.md) | Almacenamiento, aislamiento y cifrado | Propuesto |
| [ADR-0005](0005-registro-y-promocion-de-modelos.md) | Registro y promoción de modelos | Propuesto |
| [ADR-0006](0006-observabilidad-y-alertas.md) | Observabilidad y alertas | Propuesto |
| [ADR-0007](0007-flujo-terraform-plan-apply.md) | Flujo Terraform plan/apply | Aceptado |

Para una decisión nueva, copiar [`0000-template.md`](0000-template.md), asignar
el siguiente número y agregarla a este índice.
