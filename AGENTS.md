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
- **Servicios de dominio**: `CryptoService`, `SecretService`, `OrganizationService`, `MembershipService`, `ProjectService`, `EnvironmentService`, `AuthService`, `AuditService` (+ RBAC app-layer). UoW expone `organizations` / `memberships` / `audit_logs` / `refresh_tokens`.
- **Auth JWT/Argon2 (2a)**: access JWT (15 min) + refresh opaco hasheado, rotación, detección de reuso, logout / logout-all. Schemas `UserCreate`/`UserRead` alineados con `full_name`.
- **Deps FastAPI (2b)**: `get_current_user`, `get_auth_uow` / `get_user_uow` / `get_org_uow` (membership gate 403), inyección de servicios.
- **Routers `/api/v1` (Fase 3)**: auth (register/login/refresh/logout/logout-all/me), orgs + memberships, projects, environments, secrets (reveal → audit `reveal`), audit-logs (list), `/health` + `/health/ready`. Org en path (`/orgs/{org_id}/...`). CORS preparado (`CORS_ORIGINS`).
- **Roles DB**: runtime `envvault_app` (RLS) vs migraciones (`envvault_user` local / `envvault_migrate` staging-prod). `init-db.sh` crea el rol app en el primer boot de Postgres; scripts `provision_migration_role.sh` + `provision_app_role.sh` para bootstrap no-local; FastAPI/config usan `envvault_app` por defecto; Alembic usa `MIGRATION_POSTGRES_*`.
- **Tests**: suite pytest con testcontainers (Postgres real). Unitarios de KMS/crypto/auth + integración de UoW/RLS, AuthService, SecretService, dominio y HTTP (`test_auth_http`, `test_domain_http`). Los tests conectan como rol no-superuser (`envvault_app`) para que FORCE RLS sea efectivo.

### Falta (ordenado por dependencias)

Cada fase solo depende de fases anteriores. Redis corre en docker-compose pero la app aún no lo usa; `structlog` está en deps sin cablear.

#### Fase 0 — Infra DB no-local (antes del primer deploy) ✅

0. **Roles de migración staging/prod** (`envvault_migrate` vs `envvault_app`): Hecho — ver `backend/scripts/provision_migration_role.sh` + `backend/README.md`. Local sigue con `envvault_user` superuser; no bloquea desarrollo.

#### Fase 1 — Capa de dominio (sin HTTP) ✅

1. **Schemas Pydantic + repos + servicios de dominio**: Hecho — Organization, Membership, Project, Environment (DEK activa al crear), Secret, Audit (list + reveal write). Tests en `tests/integration/`.

#### Fase 2 — Autenticación núcleo

2a. **Auth mínima viable** ✅ — Argon2 + JWT access/refresh + `RefreshToken`. `AuthService` (register, login, refresh, logout, logout_all).
2b. **Dependencias FastAPI** ✅ — `CurrentUser`, UoW por contexto, inyección de servicios.
2c. **Auth extendida** (después del MVP HTTP): OAuth2 (GitHub/Google), luego 2FA/TOTP — columnas en `users` listas; no bloquea clientes.

#### Fase 3 — Routers / API de negocio ✅

3. **Routers montados** en `main.py` bajo `/api/v1` (org en path). Reveal audita; listado de audit logs expuesto.

3b. **Huecos menores de API** (opcionales, no bloquean dashboard MVP):

- Auditar mutaciones (create/update/delete/invite), no solo reveal
- Perfil / cambio de password (`UserUpdate`)
- `.env.example`
- Tabla `api_tokens` sin servicio (relevante para CLI, Fase 6)

#### Fase 4 — Hardening de la API

4. **Rate limiting con Redis** — sobre todo auth y reveal de secretos.
5. **Observabilidad** — cablear `structlog` (request id, user/org), métricas básicas si aplica.

#### Fase 5 — Empaquetado y entrega

6. **CI/CD** (GitHub Actions: lint → test → build); ampliar cobertura HTTP.
7. **Nginx** — reverse proxy / TLS. Si el pipeline despliega a staging/prod, depende de la Fase 0.

#### Fase 6 — Clientes (en paralelo entre sí; dependen de la API)

8. **Dashboard** (Vite/React)
9. **Landing** (Astro) — puede adelantarse visualmente; waitlist/CTA real pueden esperar
10. **CLI** (`envvault pull`) — necesita auth + secrets API (+ `api_tokens`)

### Próximos pasos recomendados

Orden sugerido (defensible en code review): **B → C**, luego **D**. El punto A (huecos de API para sesión/audit/ready) ya está hecho.

**B — Hardening (Fase 4)**  
Rate limit en login/register/refresh y especialmente `reveal`; cablear structlog (`request_id`, `user_id`, `org_id`). Redis ya está en compose.  
Por qué: en un vault, brute-force y reveal sin límite son el riesgo más fácil de demostrar en entrevista.

**C — CI/CD (Fase 5)**  
GitHub Actions: ruff + pytest (testcontainers). El Dockerfile y la suite ya existen.  
Por qué: cierra el círculo “production-grade” barato; no enseña dominio, pero sí higiene.

**D — Clientes o auth extendida**  
Dashboard (Vite/React) u OAuth/2FA.  
Por qué: lo visible del portfolio vs. profundidad de auth. El dashboard ya puede bootstrappear con `/auth/me` y mostrar audit logs. No empezar 2c antes de tener al menos B o un esqueleto de dashboard.
