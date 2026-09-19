# ADR-0007: Flujo Terraform plan/apply

- Estado: Aceptado
- Fecha: 2026-09-19
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

El repositorio ya separa roles OIDC de plan y apply para development. Se necesita
decidir cómo garantizar que el cambio revisado sea exactamente el aplicado, sin
credenciales permanentes ni applies automáticos desde pull requests.

## Opciones consideradas

### Opción A — Plan guardado, aprobación y apply del mismo artefacto

CI crea un plan binario, registra hashes y resumen, lo guarda con retención
corta y un workflow protegido lo aplica tras aprobación. Reduce la distancia
entre lo revisado y lo ejecutado.

### Opción B — Plan en PR y regeneración durante apply

Es más sencillo, pero el segundo plan puede diferir por drift, cambios de
provider o estado entre revisión y apply.

### Opción C — Apply automático al fusionar

Es rápido, pero contradice el requisito actual de aprobación humana y eleva el
riesgo/costo de un proyecto de aprendizaje en una cuenta real.

## Recomendación técnica

Elegir **plan guardado + aprobación en GitHub Environment + apply del mismo
artefacto**. El artefacto tendrá checksum, commit SHA, expiración corta y acceso
limitado a los roles correspondientes.

## Resolución del propietario

- Decisión: Aceptar recomendación
- Opción elegida: Opción A — plan guardado, aprobación y apply del mismo artefacto
- Justificación: evitar que el plan revisado y el aplicado difieran, manteniendo
  credenciales temporales y separación de permisos.
- Condiciones o cambios solicitados: almacenar el plan en el bucket S3 privado
  de state, bajo un prefijo restringido, con expiración automática y sin
  publicarlo como artefacto del repositorio.
- Fecha de decisión: 2026-09-19

## Consecuencias si se acepta la recomendación

- Apply falla si cambian commit, state esperado, checksum o vigencia del plan.
- El plan puede contener datos sensibles y debe manejarse como artefacto
  restringido, nunca publicarse en logs ni conservarse indefinidamente.
- Cambios urgentes siguen el mismo control; no se crean llaves de excepción.

## Validación y criterios de reversión

- Demostrar que el rol de plan no puede mutar recursos administrados.
- Demostrar que el rol de apply solo opera desde el Environment protegido.
- Probar rechazo por plan expirado, alterado o asociado a otro commit.
