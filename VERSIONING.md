# Guía de Versionado y Releases

Este documento explica cómo funciona el sistema de versionado semántico y releases automáticas del proyecto.

## Versionado Semántico

El proyecto sigue el estándar de [Versionado Semántico 2.0.0](https://semver.org/lang/es/).

### Formato: `MAJOR.MINOR.PATCH`

- **MAJOR**: Cambios incompatibles con versiones anteriores
- **MINOR**: Nueva funcionalidad compatible con versiones anteriores
- **PATCH**: Correcciones de bugs compatibles con versiones anteriores

### Ejemplos:
- `1.0.0` → `1.0.1`: Corrección de bug
- `1.0.1` → `1.1.0`: Nueva funcionalidad
- `1.1.0` → `2.0.0`: Cambio incompatible (breaking change)

## Proceso de Release

### 1. Actualizar CHANGELOG.md

Antes de crear una nueva versión, actualiza el `CHANGELOG.md`:

```markdown
## [2.1.0] - 2025-12-05

### Agregado
- Nueva funcionalidad X
- Nuevo comando Y

### Cambiado
- Mejorado comportamiento de Z

### Corregido
- Bug en módulo W
```

### 2. Crear Tag de Versión

```bash
# Crear tag para nueva versión
git tag -a v2.1.0 -m "Release v2.1.0"

# Push del tag a GitHub
git push origin v2.1.0
```

### 3. Release Automática

Al hacer push del tag, GitHub Actions:

1. ✅ Extrae automáticamente las notas del `CHANGELOG.md` para esa versión
2. ✅ Crea una GitHub Release con esas notas
3. ✅ Construye y publica la imagen Docker con tags:
   - `ghcr.io/devil1210/zeepub-bot:2.1.0` (versión exacta)
   - `ghcr.io/devil1210/zeepub-bot:2.1` (major.minor)
   - `ghcr.io/devil1210/zeepub-bot:2` (major)
   - `ghcr.io/devil1210/zeepub-bot:latest` (si es rama main)

## Tipos de Releases

### Release Estable
```bash
git tag -a v2.1.0 -m "Release v2.1.0"
```
- Se marca como "Latest Release"
- Imagen Docker tagueada como `:latest`

### Pre-release
```bash
git tag -a v2.1.0-beta.1 -m "Beta release v2.1.0-beta.1"
```
- Se marca como "Pre-release"
- NO se taguea como `:latest`
- Útil para testing antes de release estable

## Imágenes Docker

### Disponibles en GitHub Container Registry

```bash
# Última versión estable
docker pull ghcr.io/devil1210/zeepub-bot:latest

# Versión específica
docker pull ghcr.io/devil1210/zeepub-bot:2.1.0

# Major.Minor (última patch de esa serie)
docker pull ghcr.io/devil1210/zeepub-bot:2.1

# Major (última minor de ese major)
docker pull ghcr.io/devil1210/zeepub-bot:2
```

### Actualización del docker-compose.yml

Para producción, especifica siempre una versión exacta:

```yaml
services:
  zeepubs_bot:
    image: ghcr.io/devil1210/zeepub-bot:2.1.0  # Versión exacta
    # NO usar :latest en producción
```

Para desarrollo, puedes usar:

```yaml
services:
  zeepubs_bot:
    image: ghcr.io/devil1210/zeepub-bot:latest  # Última versión
```

## Workflow Completo de Release

### Paso a Paso

1. **Desarrollar cambios**
   ```bash
   git checkout -b feature/nueva-funcionalidad
   # ... hacer cambios ...
   git commit -m "feat: Agregar nueva funcionalidad"
   ```

2. **Merge a main**
   ```bash
   git checkout main
   git merge feature/nueva-funcionalidad
   git push origin main
   ```

3. **Actualizar CHANGELOG.md**
   - Editar `CHANGELOG.md`
   - Mover cambios de `[No Publicado]` a nueva versión
   - Agregar fecha de release
   ```bash
   git add CHANGELOG.md
   git commit -m "docs: Actualizar CHANGELOG para v2.1.0"
   git push origin main
   ```

4. **Crear y push tag**
   ```bash
   git tag -a v2.1.0 -m "Release v2.1.0: Descripción breve"
   git push origin v2.1.0
   ```

5. **Verificar Release**
   - Ir a GitHub → Releases
   - Verificar que la release se creó correctamente
   - Verificar que las notas del CHANGELOG se incluyeron
   - Verificar que la imagen Docker se publicó

## Convenciones de Commits

Para mantener un changelog limpio, usa [Conventional Commits](https://www.conventionalcommits.org/es/):

- `feat:` - Nueva funcionalidad (→ MINOR bump)
- `fix:` - Corrección de bug (→ PATCH bump)
- `docs:` - Solo documentación
- `refactor:` - Refactorización sin cambio funcional
- `perf:` - Mejora de rendimiento
- `test:` - Agregar/modificar tests
- `chore:` - Tareas de mantenimiento
- `BREAKING CHANGE:` en el cuerpo (→ MAJOR bump)

### Ejemplos:

```bash
git commit -m "feat: Agregar soporte para descarga en batch"
git commit -m "fix: Corregir error en extracción de metadatos"
git commit -m "docs: Actualizar README con nuevos comandos"
git commit -m "feat!: Cambiar API de configuración" # Breaking change
```

## Revertir una Release

Si necesitas revertir una release:

```bash
# Eliminar tag localmente
git tag -d v2.1.0

# Eliminar tag remotamente
git push origin :refs/tags/v2.1.0

# Eliminar release manualmente desde GitHub UI
# (No hay forma automática de eliminar releases)
```

## Troubleshooting

### Release no se creó automáticamente
- Verificar que el tag tiene el prefijo `v` (ej: `v2.1.0`, no `2.1.0`)
- Verificar logs en GitHub Actions
- Asegurar que el workflow tiene permisos de `contents: write`

### Imagen Docker no se publicó
- Verificar que el tag es semántico válido (ej: `v2.1.0`)
- Verificar que el workflow de Docker se ejecutó
- Verificar permisos del GITHUB_TOKEN para packages

### Notas del CHANGELOG no aparecen
- Verificar que el formato en CHANGELOG.md es: `## [2.1.0]`
- El número de versión debe coincidir exactamente (sin el prefijo `v`)
- Debe haber una sección con ese número en CHANGELOG.md
