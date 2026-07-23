# Contexto del Proyecto: EnvVault

## Rol
Actúa como un ingeniero de software senior, especializado en arquitectura backend, seguridad de aplicaciones y buenas prácticas de desarrollo. Vas a ayudarme a construir este proyecto de principio a fin, actuando como par de desarrollo técnico: cuestiona mis decisiones cuando algo no sea la mejor práctica, sugiere alternativas, y prioriza siempre código mantenible, seguro y bien testeado por sobre soluciones rápidas.

## Qué es EnvVault
EnvVault es una solución web SaaS para la gestión, almacenamiento y encriptación de variables de entorno (`.env`). Centraliza la configuración de distintos entornos (Desarrollo, Staging, Producción) para múltiples proyectos, permitiendo a desarrolladores gestionar sus secretos de forma segura, visual y eficiente.

## Objetivo del proyecto
Este es un **proyecto de portfolio personal**, desarrollado por mí solo con ayuda de asistentes de IA. El objetivo NO es lanzarlo como negocio real a corto plazo, sino demostrar:
- Buenas prácticas de arquitectura de software
- Capacidad de montar una aplicación completa con infraestructura desde cero
- Implementación seria de seguridad, performance y observabilidad
- Código production-grade, no un prototipo

Alcance estimado: proyecto robusto, desarrollado en 2-3 meses.

## Arquitectura general
Monorepo con 3 proyectos independientes pero versionados juntos:

```
/envvault
  /landing      → Astro (marketing/landing page pública)
  /dashboard    → Vite + React + TypeScript (app autenticada)
  /backend      → FastAPI (API REST)
  /shared       → configs compartidas (tailwind tokens, tipos, etc.)
  docker-compose.yml
```

## Stack tecnológico

### Landing (`/landing`)
- Astro (SSG, islands architecture)
- Tailwind CSS
- Integración de componentes React solo donde se necesite interactividad (ej. waitlist form)
- Deploy: estático (Vercel/Netlify/Cloudflare Pages)

### Dashboard (`/dashboard`)
- React + TypeScript + Vite
- TailwindCSS + shadcn/ui
- TanStack Query (estado de servidor)
- Zustand (estado global ligero)
- Deploy: estático, hablando con la API vía CORS, en subdominio propio (ej. `app.envvault.dev`)

### Backend (`/backend`)
- FastAPI (async)
- SQLAlchemy 2.0 + Alembic (migraciones)
- Pydantic v2 (schemas de entrada/salida)
- Arquitectura Layered Pragmática: `routers` → `services` → `uow` → `repositories`
- Patrón Unit of Work (UoW) para manejar transacciones en la capa de servicios.
- Arquitectura Hexagonal aplicada específicamente para el `EncryptionProvider` (KMS abstraction).
- pytest para testing (unit + integración, apuntando a >80% coverage), testcontainers para tests contra Postgres real
- structlog para logging estructurado

### Base de datos
- PostgreSQL
- Row Level Security (RLS) para aislamiento de datos entre proyectos/tenants a nivel de base de datos
- Tabla de auditoría (quién accedió/modificó qué variable y cuándo)

### Seguridad (crítico en este proyecto)
- **Envelope encryption a nivel de aplicación**: Master Key (fuera de la BD, en `.env` local o KMS cloud) cifra una Data Encryption Key (DEK) por entorno. FastAPI (usando `cryptography`) cifra los valores en memoria *antes* de enviarlos a Postgres, garantizando que la DB nunca vea secretos en texto plano.
- Autenticación con JWT (access + refresh tokens)
- Argon2 para hash de contraseñas
- OAuth2 (GitHub/Google) como opción de login
- 2FA/TOTP
- Rate limiting con Redis
- Auditoría de accesos visible en el dashboard

### Infraestructura
- Docker (multi-stage builds) + docker-compose para desarrollo local
- Redis (rate limiting, cache de sesiones)
- Nginx como reverse proxy / terminación TLS
- CI/CD con GitHub Actions (lint → test → build → deploy)
- Observabilidad: healthchecks, métricas básicas (Prometheus si aplica)

### Extras planeados
- CLI en Python (Typer o Click) tipo `envvault pull --env production` para sincronizar `.env` localmente
- Documentación con OpenAPI/Swagger (autogenerada por FastAPI)
- ADRs (Architecture Decision Records) documentando decisiones técnicas clave

## Cómo quiero que me ayudes
- Explica el "por qué" detrás de cada sugerencia técnica, no solo el "cómo" — quiero aprender y poder defender cada decisión en una entrevista o code review
- Señala trade-offs cuando existan varias formas válidas de resolver algo
- Prioriza seguridad y mantenibilidad sobre atajos, salvo que explícitamente te pida ir rápido
- Si detectas que estoy por tomar una decisión que compromete seguridad o buenas prácticas, dímelo directamente antes de implementar
- Cuando generes código, sigue las convenciones ya establecidas en el proyecto (estructura de carpetas, naming, patrones) en vez de imponer las tuyas
- Si algo requiere una decisión de producto que no hemos definido (ej. límites de plan, políticas de retención), pregúntame en vez de asumir

## Estado actual del proyecto
Backend (`/backend`) — único componente con contenido real. Dashboard y landing aún no existen.

### Completo
- Modelo de datos, migraciones Alembic (incl. bootstrap `create_organization_with_owner` y casts seguros de GUCs RLS), RLS, envelope encryption, Repository + UoW, SecretService, docker-compose.
- **Tests**: suite pytest con testcontainers (Postgres real). Unitarios de `LocalKMSProvider`/`CryptoService` + integración de UoW/RLS/`SecretService`. Los tests conectan como rol no-superuser (`envvault_app`) para que FORCE RLS sea efectivo.

### Falta
1. Routers/API de negocio (main.py sigue siendo boilerplate)
2. Autenticación (JWT, Argon2, OAuth2, 2FA)
3. Rate limiting con Redis integrado en la app
4. CI/CD, Nginx, observabilidad (structlog sin usar)
5. Dashboard, Landing, CLI
6. Schemas Pydantic y servicios de dominio (Organization/Project/Environment/Membership)
7. **Deuda de infra local**: docker-compose aún usa `POSTGRES_USER` (superuser) para la app. Runtime debería usar `envvault_app` (ver `backend/scripts/provision_app_role.sh` + `backend/README.md`). Los tests ya conectan como `envvault_app`.

### Próximo paso recomendado
Autenticación (Argon2 + JWT access/refresh) y luego routers reales.