# Auth & RBAC

## Model

- **Authentication:** local email/password with bcrypt hashing (cost 12) + HS256 JWT.
- **Refresh tokens:** persisted in MongoDB (`refresh_tokens` collection, TTL index), rotated on every `/api/auth/refresh`. Old jti is revoked.
- **Sessions:** stateless bearer tokens sent as `Authorization: Bearer <token>`. Frontend stores them in `localStorage`. Refresh flow triggered by 401 interceptor.
- **CORS:** driven by `CORS_ORIGINS` env — comma-separated list, or `*` for any (dev only). Production must pin to the exact FQDN.

## Roles

| Role | Capabilities |
|---|---|
| **admin**      | Everything. User management. Provider config. All CRUD. |
| **developer**  | Strategy engineering (create/delete), research queries, provider view, code paths. |
| **researcher** | Strategy create (no delete), research queries, provider view. |
| **operator**   | Read-only on strategies + provider view. Ops surfaces (health, deploy). |
| **viewer**     | Read-only on strategies. No research, no admin. |

Roles are enforced with `require_roles(...)` dependencies. Example:

```python
@router.post("", response_model=StrategyOut, status_code=201)
async def create_strategy(
    req: StrategyCreate,
    user: UserPublic = Depends(require_roles("admin", "developer", "researcher")),
):
    ...
```

The frontend mirrors this — the sidebar navigation is filtered by role, and `<ProtectedRoute roles={[...]}>` is used per page.

## Endpoints

Public (no auth):
- `POST /api/auth/login`  →  issues access + refresh
- `POST /api/auth/refresh`  →  rotates refresh + issues new access
- `GET  /api/health`, `GET /api/readiness`, `GET /api/version`

Authenticated:
- `POST /api/auth/logout`
- `GET  /api/auth/me`
- `GET  /api/dashboard/summary`
- `GET/POST/DELETE /api/strategies/**` (role-filtered)
- `POST /api/research/query`, `GET /api/research/history` (admin/developer/researcher)
- **Admin-only** (`require_admin()`):
  - `GET/POST/PATCH/DELETE /api/admin/users/**`
  - `GET /api/admin/providers`

## JWT shape

Access token:
```json
{
  "sub": "<user_id>",
  "email": "admin@strategy-factory.local",
  "role": "admin",
  "type": "access",
  "iat": 1738396800,
  "exp": 1738400400
}
```

Refresh token:
```json
{
  "sub": "<user_id>",
  "jti": "<uuid>",
  "type": "refresh",
  "iat": 1738396800,
  "exp": 1739001600
}
```

Both signed with `JWT_SECRET` (HS256). TTLs from `JWT_ACCESS_TTL_MIN` (default 60) and `JWT_REFRESH_TTL_DAYS` (default 7).

## Admin seeding (idempotent)

At every backend startup, `seed_admin()`:
1. If `ADMIN_EMAIL` or `ADMIN_PASSWORD` is unset → skip with a warning log (no crash).
2. If the admin doesn't exist → insert with hashed password.
3. If it exists but the password hash doesn't match `ADMIN_PASSWORD` → update the hash in place.
4. If it exists but role ≠ `admin` or status ≠ `active` → fix them.

Safe to run repeatedly. This is what makes `deploy.sh` idempotent for the bootstrap admin.

## Modular auth (future SSO)

The auth surface is deliberately narrow:
- Login/logout/refresh/me on the backend.
- Frontend uses an `AuthContext` and the `api.js` interceptor.

Swapping to Keycloak / Authentik / Google OIDC:
1. Replace `security.py` token creation with an external provider callback flow.
2. Keep `get_current_user(...)` as the single validation point — swap the decode path but keep the `UserPublic` shape.
3. Users still live in Mongo; external auth resolves to a local `user_id`.
4. `RefreshToken` collection can be dropped (issuer handles this).
5. All routes and role guards stay unchanged.

## Password rules

- Minimum length 8 (enforced on create/update).
- No client-side complexity gate (internal-only platform; use company policy).
- Server never stores plaintext, and never logs it.
