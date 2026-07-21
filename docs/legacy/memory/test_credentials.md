# Test credentials

Seeded by `backend/auth_utils.seed_admin()` on first boot of the canonical backend.

## Admin user (full operator access)

| Field | Value |
|---|---|
| Email | `admin@strategyfactory.dev` |
| Password | `vad4lXbPkQKqokvMde8KhtqL` |
| Role | `admin` |
| Status | `approved` |
| user_id | `b147d6e2545e` |

## Sign-in flow

1. Open the preview URL.
2. AuthGate renders with email + password fields.
3. Submit credentials above → JWT issued, valid for 24 h.
4. CommandShell loads with full admin access (11 top tabs incl. **Admin**).

## API auth

```bash
API="https://strategy-factory-v1.preview.emergentagent.com"

TOKEN=$(curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@strategyfactory.dev","password":"vad4lXbPkQKqokvMde8KhtqL"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

curl -s "$API/api/latent/feature-flags" -H "Authorization: Bearer $TOKEN"
```

## Notes

* Credentials sourced from `backend/.env` (`ADMIN_EMAIL`, `ADMIN_PASSWORD`) — set during hydration per HYDRATION_PLAN.md §5.1 Option C.
* JWT signing key: `JWT_SECRET` in `backend/.env` (256-bit hex).
* Token expires after 24 h — re-login if 401 received.
* Admin user is auto-seeded on every boot if missing (idempotent).
