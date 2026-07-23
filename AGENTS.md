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

- **Envelope encryption a nivel de aplicación**: Master Key (fuera de la BD, en `.env` local o KMS cloud) cifra una Data Encryption Key (DEK) por entorno. FastAPI (usando `cryptography`) cifra los valores en memoria _antes_ de enviarlos a Postgres, garantizando que la DB nunca vea secretos en texto plano.
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

- Modelo de datos, migraciones Alembic (incl. bootstrap `create_organization_with_owner`, casts seguros de GUCs RLS, GRANTs DML a `envvault_app`, SELECT de memberships entre peers vía `user_is_org_member`), RLS, envelope encryption, Repository + UoW, docker-compose.
- **Servicios de dominio**: `CryptoService`, `SecretService`, `OrganizationService`, `MembershipService`, `ProjectService`, `EnvironmentService` (+ RBAC app-layer). UoW expone `organizations` / `memberships`.
- **Roles DB**: runtime `envvault_app` (RLS) vs migraciones (`envvault_user` local / `envvault_migrate` staging-prod). `init-db.sh` crea el rol app en el primer boot de Postgres; scripts `provision_migration_role.sh` + `provision_app_role.sh` para bootstrap no-local; FastAPI/config usan `envvault_app` por defecto; Alembic usa `MIGRATION_POSTGRES_*`.
- **Tests**: suite pytest con testcontainers (Postgres real). Unitarios de KMS/crypto + integración de UoW/RLS, `SecretService` y servicios de dominio. Los tests conectan como rol no-superuser (`envvault_app`) para que FORCE RLS sea efectivo.

### Falta (ordenado por dependencias)

El orden anterior listaba routers antes que schemas/servicios y auth; eso invertía el grafo real (`routers → services → uow → repos`, con `user_id`/`org_id` desde JWT). Abajo, cada fase solo depende de fases anteriores.

`main.py` sigue siendo boilerplate (sin routers). Auth aún no existe.

#### Fase 0 — Infra DB no-local (antes del primer deploy) ✅

0. **Roles de migración staging/prod** (`envvault_migrate` vs `envvault_app`): Hecho — ver `backend/scripts/provision_migration_role.sh` + `backend/README.md`. Local sigue con `envvault_user` superuser; no bloquea desarrollo.

#### Fase 1 — Capa de dominio (sin HTTP) ✅

1. **Schemas Pydantic + repos + servicios de dominio**: Hecho — Organization (vía `create_organization_with_owner`), Membership (RBAC viewer read-only), Project, Environment (DEK activa al crear), UoW con `organizations`/`memberships`. AuditLog opcional pendiente. Tests en `tests/integration/test_domain_services.py`.

#### Fase 2 — Autenticación núcleo

2a. **Auth mínima viable**: Argon2 + JWT access/refresh + `RefreshToken`. Alinear schemas (`UserCreate`/`UserRead` vs `full_name`). `AuthService` (register, login, refresh, logout). Sin OAuth ni 2FA todavía.
2b. **Dependencias FastAPI**: `get_current_user`, `get_org_context`, `get_uow(user_id, org_id)`, inyección de servicios.
2c. **Auth extendida** (después de 2a y routers básicos): OAuth2 (GitHub/Google), luego 2FA/TOTP — no bloquea el MVP HTTP.

#### Fase 3 — Routers / API de negocio

3. **Montar routers en FastAPI** (reemplazar boilerplate de `main.py`), en este orden:
   1. `auth` — register/login/refresh
   2. `organizations` / `memberships`
   3. `projects` / `environments`
   4. `secrets` — delegar a `SecretService` (reveal → audit `reveal`)
   5. Healthcheck (`/health`) — útil para Docker/Nginx/CI

   Convención sugerida: `/api/v1/...` con org en path o header (`X-Organization-Id`).

#### Fase 4 — Hardening de la API

4. **Rate limiting con Redis** — sobre todo auth y reveal de secretos.
5. **Observabilidad** — cablear `structlog` (request id, user/org), métricas básicas si aplica.

#### Fase 5 — Empaquetado y entrega

6. **CI/CD** (GitHub Actions: lint → test → build); ampliar con tests HTTP de la Fase 3.
7. **Nginx** — reverse proxy / TLS. Si el pipeline despliega a staging/prod, depende de la Fase 0.

#### Fase 6 — Clientes (en paralelo entre sí; dependen de la API)

8. **Dashboard** (Vite/React)
9. **Landing** (Astro) — puede adelantarse visualmente; waitlist/CTA real pueden esperar
10. **CLI** (`envvault pull`) — necesita auth + secrets API

### Próximo paso recomendado

Auth JWT/Argon2 + deps FastAPI (`CurrentUser`, `OrgContext`, UoW), luego routers que expongan los servicios de dominio ya existentes.
