# ADR-0009: Convención de tags y retención de imágenes en ECR

- Estado: Propuesto
- Fecha: 2026-11-16
- Propietario: Gonzalo
- Decisores: Gonzalo
- Reemplaza a: No aplica
- Reemplazado por: No aplica

## Contexto

El endpoint de ADR-0008 usa la imagen de serving
`mlops/docker/sagemaker-inference.Dockerfile`, guardada en un repositorio ECR
con tags **inmutables**. El `SageMaker Model` referencia la imagen **por
digest** (ADR-0005), así que el tag no decide qué se ejecuta. Sirve a dos
consumidores:

1. la persona que lee la consola de ECR o un manifiesto de promoción;
2. la política de ciclo de vida, que filtra imágenes por patrón de tag.

La versión de la imagen no es la versión del modelo. El modelo `0.1.0` vive en
`model.tar.gz`; agregar la captura de ADR-0008 cambia la imagen y no el modelo.

ADR-0005 exige que ECR conserve la imagen del campeón vigente y las imágenes
dentro de la ventana de rollback.

Comportamiento de las políticas de ciclo de vida, verificado en la
documentación de AWS el 2026-11-16:

- Una imagen la expira como máximo una regla. Una imagen que coincide con una
  regla no puede ser expirada por otra de menor prioridad (número mayor).
- `tagPatternList` y `tagPrefixList` solo se usan con `tagStatus = tagged`, y
  una regla no puede usar los dos.
- `imageCountMoreThan` ordena por fecha de subida y expira las más antiguas
  que excedan el número indicado. No sabe qué imagen está desplegada.
- Las imágenes se expiran dentro de las 24 horas posteriores a cumplir el
  criterio.

## Drivers de decisión

- Saber, sin consultar Git, qué versión es una imagen y de qué commit viene.
- Reconstruir una imagen (por ejemplo, para parchear la imagen base) sin chocar
  con la inmutabilidad de los tags.
- Que las pruebas no consuman los lugares reservados al rollback.
- Costo de almacenamiento bajo.

## Opciones consideradas

### Opción A — Semver puro (`0.2.0`)

Es fácil de leer. Una reconstrucción de la misma versión obliga a subir la
versión aunque el código no cambie, y el tag no dice de qué commit salió.

### Opción B — SHA corto del commit (`a1b2c3d`)

Trazable al código exacto y fácil de generar en CI. No indica orden ni versión
sin consultar Git.

### Opción C — Compuesto `v<semver>-<sha7>` (`v0.2.0-a1b2c3d`)

Legible y trazable. Una reconstrucción produce otro SHA, por lo que no choca
con la inmutabilidad. El prefijo `v` sirve como filtro de ciclo de vida.

### Opción D — Fecha (`2026-11-16`)

El orden es obvio, pero no dice versión ni commit y dos builds del mismo día
chocan.

## Recomendación técnica

Elegir la **Opción C** con dos familias de tags separadas:

| Familia | Formato | Quién la sube | Retención |
|---|---|---|---|
| Release | `v<semver>-<sha7>`, por ejemplo `v0.2.0-a1b2c3d` | solo el workflow de CI desde `main` | las **10** más recientes |
| Desarrollo | `dev-<sha7>` | una persona con `mlops/scripts/push-serving-image-dev.sh` | 7 días desde la subida |
| Sin tag | — | quedan al sobrescribir capas | 1 día desde la subida |

- `<semver>` sale de `mlops/docker/sagemaker-inference.version`, que también
  se inyecta en la imagen como `IMAGE_VERSION` y aparece en cada línea de
  captura.
- La política tiene tres reglas con patrones disjuntos: `untagged`
  (prioridad 1), `dev-*` (prioridad 2) y `v*` (prioridad 3).
- Separar `dev-` de `v` impide que diez builds de prueba expulsen la imagen del
  campeón.
- Antes de subir un release, el workflow comprueba que la imagen desplegada en
  el endpoint seguirá entre las 10 imágenes de release más recientes. Si no,
  el push falla. Con un release al mes o menos, 10 imágenes equivalen a muchos
  meses de rollback.
- Si un tag ya existe (el mismo commit se publicó antes), el workflow no vuelve
  a subirlo.

## Resolución del propietario

- Decisión: [ ] Aceptar recomendación / [ ] Elegir otra opción / [ ] Rechazar
- Opción elegida:
- Justificación:
- Condiciones o cambios solicitados:
- Fecha de decisión:

## Consecuencias

### Positivas

- Cada tag de release identifica versión y commit.
- Las pruebas no compiten con los releases por la retención.
- El almacenamiento de 10 imágenes de unos cientos de MB cuesta centavos al mes.

### Negativas y compromisos

- La versión de la imagen se mantiene a mano en un archivo; olvidarse de
  subirla deja dos releases con el mismo semver y distinto SHA.
- La comprobación previa al push solo protege la imagen desplegada en el
  endpoint, no una configuración anterior que alguien quiera restaurar.
- Un tag `dev-` subido desde un commit local no garantiza que ese commit exista
  en GitHub.

## Validación y criterios de reversión

- La vista previa de la política de ciclo de vida en ECR no marca ninguna
  imagen `v*` mientras haya 10 o menos.
- Diez imágenes `dev-` subidas seguidas no expiran ninguna imagen `v*`.
- Un segundo push del mismo commit no falla ni crea otra imagen.
- Revisar el número 10 si la frecuencia de releases supera uno por semana.

## Referencias

- [ADR-0005](0005-registro-y-promocion-de-modelos.md)
- [ADR-0008](0008-endpoint-serverless-con-captura-propia.md)
- [Lifecycle policies en Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html)
