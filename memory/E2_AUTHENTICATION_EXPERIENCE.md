# E2 — Authentication Experience

> The complete lifecycle of an operator's relationship with the
> Factory: **first login · returning login · session lifetime ·
> session expiry recovery · multi-mode users · logout**.
>
> Auth is the door — the door must feel like the rest of the house.
> Consistency, restraint, and craftsmanship apply from the very first
> pixel the operator sees.
>
> Layered on **Bible v2.1**. Reuses D6 modes, D7 State Template, E1
> Strategy Passport (post-auth landing target).
>
> Prepared 2026-07-20. Second E-series deliverable per D8 §13.6.

---

## 0. Design Principles Checklist (18 items — permanent quality gate)

E2 confirms:

- [x] **Invisible Luxury** — no marketing on the login screen; no illustrations; no product tagline; no *"Welcome to Strategy Factory!"* fanfare. The door is Concept A, unmistakably ours from the first frame.
- [x] **Everything Connected** — after auth, the operator lands on the surface they were trying to reach (or Mission Control for first-time); auth does not sever their intended context.
- [x] **Progressive Disclosure** — Advanced Lens on the login screen (rare) reveals session-token status; ordinary auth is a single-input flow.
- [x] **Evidence First** — session state is visible in the user menu; provenance of the current session (issued-at, expires-at) surfaces on demand.
- [x] **Persona Awareness** — mode is claimed *during* auth (SSO claim or default = Operations); mode switcher available immediately post-auth.
- [x] **Mission Control First** — post-auth landing for Operations is `/c/mission`; for other modes per D6 §12.
- [x] **Accessibility (WCAG 2.2 AA)** — login form is keyboard-first; focus lands on email field on mount; screen-reader-announces every validation state.
- [x] **Motion Discipline** — login → landing is a 400 ms Editorial-tier crossfade (Bible §6.1 Editorial). No spinners; optimistic-UI validation (§6.3).
- [x] **Design Token Compliance** — same tokens as the rest of the app; no login-only styles.
- [x] **Six-Signal Rule** — auth errors use `--sig-warn` (retryable) never `--sig-crit`; kill-posture stays `--sig-crit` even on login screen.
- [x] **Lineage Validation** — user session is itself an artefact with provenance (issued by, at, expires); visible in Advanced Lens.
- [x] **Empty-State Quality** — every non-happy auth state (session-expired, locked, invite-invalid, kill-posture-armed, network-down) has an authored State Template specimen from D7.
- [x] **Consistency** — login screen wears the shell chrome's status rail (kill posture visible even before auth); no separate design system for auth.
- [x] **Explainability** — every auth error says exactly *what* is wrong and *what* to do (never *"Invalid credentials"*).
- [x] **Storytelling Copy Standard (D2 Addendum)** — Division voice applies: *"Your session has expired · sign in again to resume."* Not *"401 Unauthorized"*.
- [x] **Context Never Lost (Bible §1.4.4)** — a URL requiring auth preserves its full query payload through the login flow; post-auth returns to the intended URL exactly as attempted.
- [x] **State Memory (Bible §1.4.5)** — session-expiry recovery restores the operator's exact vantage point (scroll, expanded panels) on the surface they were on when the session expired.
- [x] **Decision Identity (D6 §8.1a)** — the same account, when authed into any of its assigned modes, sees the same underlying entitlements; only the mode's presentation differs.
- [x] **Trust Before Credentials (§9)** — the disabled pre-auth shell displays non-sensitive operational signals (health · kill posture · env · UTC time · platform status) so the operator feels they are approaching a live operational system before they type a character.

---

## 1. Purpose

Authentication is a *gate*, and gates are moments of design opportunity.
Most products treat login as a chore; this one treats it as a
brand-defining first frame.

**E2 codifies:**

1. **How an operator enters the Factory** — first login and every
   return.
2. **How the session lives and dies** — TTL, activity extension,
   expiry recovery.
3. **How multiple modes are assigned and switched.**
4. **How auth failures land legibly.**
5. **How the shell chrome persists across auth boundaries** — kill
   posture visible on the login screen; approvals count masked but
   architecture preserved.

**Anti-goals:**

- Marketing / "trust badges" / illustrated hero images on the login
  screen.
- "Remember me" checkbox (session policy is deterministic, not
  operator-chosen).
- Self-signup — Strategy Factory is a closed system; users are
  invited.
- Social login on the operator surface (SSO with corporate identity
  provider is later; not Sprint 1).
- Passwordless-only — password remains the default; passwordless is a
  future enhancement.
- "Welcome back!" greetings on landing after auth (violates D6 anti-
  patterns).

---

## 2. Auth stances (the four states of an operator)

| Stance | Meaning | Landing behaviour |
|---|---|---|
| **Anonymous** | No session cookie; unknown operator | Login screen |
| **Authenticated** | Valid session; identity known; mode claimed | Mode-default landing (D6 §12) |
| **Expired** | Session cookie present but past TTL | Login screen with recovery banner |
| **Locked** | Rate-limited or admin-locked account | Login screen with lockout notice |

The four stances are mutually exclusive. Transitions between them are
the auth flow itself.

---

## 3. The login screen (Anonymous → Authenticated)

### 3.1 Layout

The login screen is **not a stripped-down design**; it is the same shell
chrome the operator sees post-auth, with the main content area
occupied by a single centred card.

```
┌────────────────────────────────────────────────────────────────────┐
│  Strategy Factory                                        ⌘K disabled│  ← Header (identical to authed shell)
│                                                                    │
├─────┬──────────────────────────────────────────────────────────────┤
│     │                                                              │
│ L   │                                                              │
│ e   │            ┌────────────────────────────────┐                │
│ f   │            │                                │                │
│ t   │            │  Sign in                       │                │
│     │            │                                │                │
│ r   │            │  email                         │                │
│ a   │            │  ┌──────────────────────────┐  │                │
│ i   │            │  │                          │  │                │
│ l   │            │  └──────────────────────────┘  │                │
│     │            │                                │                │
│     │            │  password                      │                │
│     │            │  ┌──────────────────────────┐  │                │
│     │            │  │                          │  │                │
│     │            │  └──────────────────────────┘  │                │
│     │            │                                │                │
│     │            │  [ Sign in →             ]     │                │
│     │            │                                │                │
│     │            │  If you don't have an account, │                │
│     │            │  contact your admin.           │                │
│     │            │                                │                │
│     │            └────────────────────────────────┘                │
│     │                                                              │
├─────┴──────────────────────────────────────────────────────────────┤
│  StatusRail (6 chips)                                              │  ← Kill posture visible pre-auth
└────────────────────────────────────────────────────────────────────┘
```

**Rules:**

- **Shell chrome persists.** LeftRail visible but disabled (locked icon
  on each module). StatusRail always visible (kill-posture is public
  by design). Right rail hidden pre-auth (no timeline before identity).
- **Login card:** `--surface-1` background; 1 px `--stroke-1` border;
  `--radius-3` (12 px); max-width 320 px; centred vertically and
  horizontally in main content area.
- **Typography:** heading `--font-h2` sans; labels `--font-caption`
  UPPERCASE spaced; input text `--font-body` sans.
- **Primary action:** filled `--sig-info` button, `Sign in →`. Verb,
  arrow, right-aligned.
- **No secondary action** (no "forgot password" here; password recovery
  is admin-mediated per Sprint 1 · §4.5).
- **Contact footer:** *"If you don't have an account, contact your
  admin."* — deliberately terse; no self-signup path.

### 3.2 Interaction behaviour

- Focus lands on email field on mount (`autofocus`).
- Tab order: email → password → sign-in button.
- Enter submits from any field.
- On submit:
  - Latency budget: 300 ms (§6.3).
  - Button shows `Signing in…` in the same button, no spinner outside.
  - Optimistic UI: after 200 ms, if backend hasn't responded, the
    button shows a subtle inline pulse (Concept-B).
  - On success: 400 ms Editorial crossfade to intended landing.
  - On failure: inline error appears below password field; button
    resets to `Sign in →`; focus returns to password field.

### 3.3 Validation states

Validation happens on blur + on submit. Never on keystroke (respects
operator focus).

| State | Copy | Colour |
|---|---|---|
| Field empty on submit | *"Email is required."* / *"Password is required."* | `--sig-warn` |
| Email format invalid | *"Enter a valid email address."* | `--sig-warn` |
| Credentials incorrect | *"Email or password is incorrect."* — never say which | `--sig-warn` |
| Account locked | *"Account is temporarily locked. Try again in 15 minutes or contact your admin."* | `--sig-warn` |
| Session expired (from previous session) | *"Your session expired. Sign in again to resume."* | `--sig-info` — informational |
| Backend unreachable | *"Sign-in service is unavailable. Retrying in 8 s."* | `--sig-warn` + auto-retry |
| Kill posture on login attempt | Password still accepted; post-auth danger ribbon fires immediately | *(no login-blocking)* |

**Never on the login screen:**

- ❌ *"Invalid credentials"* (jargon).
- ❌ *"HTTP 401 Unauthorized"* (mechanism).
- ❌ Distinguishing "email not found" from "password wrong" (enumeration
  risk).
- ❌ CAPTCHA (breaks premium positioning; rate-limit + admin-lock
  policy instead).

---

## 4. Session lifecycle

### 4.1 Session TTL & extension

- **Session TTL: 8 hours** (matches operator shift).
- Session token stored in **httpOnly `SameSite=Strict` cookie**.
- **Sliding window:** session extends by 8 hours on any authenticated
  request (activity extends life).
- **Absolute maximum:** 24 hours from initial login (hard ceiling; user
  must re-auth once per day regardless of activity).

### 4.2 Session state visibility

The current session is visible under the user menu (top-right):

```
[ user · admin ▾ ]
┌────────────────────────────┐
│  admin@coinnike.com        │
│  ● operations mode          │
│                             │
│  Session                    │
│  · signed in 07:12          │
│  · extends every action     │
│  · expires 15:12 or sooner  │
│                             │
│  ⌘M · switch mode           │
│  ⌘L · sign out              │
└────────────────────────────┘
```

Advanced Lens adds:
```
  · session id  sess_ab12cd34…
  · issued by   auth.strategy-factory
  · expires at  2026-07-20T15:12:00Z
```

### 4.3 Idle detection (optional Sprint 3+)

Not in Sprint 1. Idle-timeout as a security policy is a Sprint 3+
decision alongside 2FA and SSO. Sprint 1 relies on the 8h TTL only.

---

## 5. Session expiry recovery

The most emotionally important moment in auth: an operator returns to
a surface, and their session has expired.

### 5.1 Detection

- Any authenticated request that returns `401` triggers the expiry
  flow.
- The workspace state store notices; does not clear yet.
- The current URL (including all CNL query params) is captured as the
  `next` destination.

### 5.2 Recovery flow

1. **Screen shifts to login state** — the shell chrome remains; the
   current module fades to 30 % opacity; a login card appears overlay-
   centred (`--elev-2` shadow).
2. **Copy specimen** (D7 style):
   ```
   Icon        clock · muted
   Headline    Your session expired.
   Purpose     Sign in again to resume where you left off.
   ```
3. **Login form** below the message, focused on email.
4. On successful re-auth:
   - Session cookie refreshed.
   - Login overlay dismisses with 400 ms Editorial crossfade.
   - Underlying module returns to full opacity — **scroll position
     preserved · expanded panels preserved · Evidence Drawer state
     preserved** (Bible §1.4.5 State Memory).
   - URL unchanged (CNL preserved).
   - Timeline records: *"Operator re-authenticated after session
     expiry."* (Advanced-Lens only — not a spammy row).

### 5.3 Recovery from Anonymous stance (fresh tab, no CNL)

If the operator opens a fresh browser tab with a Strategy Factory URL
that requires auth:

1. Standard login screen renders (§3).
2. URL captured as `?next=<encoded>` invisibly.
3. On successful auth: navigates to `<next>` if valid, otherwise
   mode-default landing (D6 §12).

### 5.4 Rule of Fresh Deep Link (Bible §1.4.5) still applies

A URL shared to a *different* operator lands them per their own mode
default; the sender's State Memory does not transmit through URLs.

---

## 6. First-login flow (invitation → Anonymous → Authenticated)

New operators receive an invitation from admin. Sprint 1 does **not**
implement the invitation flow UI; the admin creates the account
directly. First-time UX proper is E3.

For Sprint 1, first-login is:

1. Admin provides email + temporary password out-of-band.
2. Operator enters at login screen.
3. Post-auth: mandatory password change if `must_change_password` flag
   is set (backend-side flag; Sprint 1 respects it).
4. Landing: Mode default per D6 §12 (Operations for first-time users
   without explicit mode assignment).

### 6.1 Mandatory password change screen (post-auth, first-time only)

Rendered as a full-viewport overlay after successful auth if
`must_change_password` is true:

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│              ┌────────────────────────────────┐                    │
│              │  Set a new password            │                    │
│              │                                │                    │
│              │  Your account requires a new   │                    │
│              │  password before you continue. │                    │
│              │                                │                    │
│              │  new password                  │                    │
│              │  ┌──────────────────────────┐  │                    │
│              │  │                          │  │                    │
│              │  └──────────────────────────┘  │                    │
│              │                                │                    │
│              │  confirm new password          │                    │
│              │  ┌──────────────────────────┐  │                    │
│              │  │                          │  │                    │
│              │  └──────────────────────────┘  │                    │
│              │                                │                    │
│              │  [ Set password →         ]    │                    │
│              │                                │                    │
│              │  Rules:                        │                    │
│              │  · 12 characters minimum       │                    │
│              │  · mix of letters and numbers  │                    │
│              │  · one symbol                  │                    │
│              │                                │                    │
│              └────────────────────────────────┘                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**No skip.** No back button. This is a gate.

**Post-completion:** mode-default landing (D6 §12).

---

## 7. Logout

### 7.1 Trigger

- `⌘L` shortcut anywhere in the workspace.
- User menu → `Sign out`.

### 7.2 Confirmation

Logout is a *deliberate* action. It should not require confirmation for
routine cases (respect operator agency), but the workspace state should
be preserved for a graceful re-entry.

Behaviour:
1. Session cookie cleared immediately.
2. workspace state store: **mode + Advanced Lens + density preserved**
   in localStorage (returns after re-auth).
3. workspace state store: **CNL fields cleared** (session-scoped —
   the next operator on this browser should start fresh).
4. Redirect to login screen.
5. Timeline records nothing (logout is not a factory event).

### 7.3 Multi-tab logout (Sprint 3+)

Sprint 1 does not synchronise logout across tabs. If the operator has
Strategy Factory open in two tabs and logs out of one, the other tab
retains its session until it next makes an authenticated request that
returns 401. This is acceptable for Sprint 1.

---

## 8. Multi-mode users

### 8.1 Mode assignment

Per D6 §13, modes are not roles but *presentation preferences*. Any
authenticated user can be assigned any subset of the four modes.

**Assignment source order** (workspace state store on auth):

1. Backend user record `modes: string[]` — the authoritative list of
   assigned modes.
2. Backend user record `default_mode: string` — the default post-login
   landing mode.
3. localStorage `strategyFactory.mode` — the operator's last-used mode
   (if it's in their assigned modes; otherwise fall back to
   `default_mode`).

### 8.2 Mode switcher visibility

The mode switcher (D6 §3.1) chip only shows modes the user is
authorised for. If a user has only Operations, no chip is rendered —
mode is deterministic.

### 8.3 Mode assignment editing

Sprint 1 does **not** implement a user-facing edit UI. Admin edits
directly in the backend. Sprint 3 delivers `/c/advanced/users` for
mode-assignment editing (D6 §13).

---

## 9. Trust Before Credentials — pre-auth operational signals

Before authentication, the operator should already feel they are
approaching a **live operational system** — not a hosted marketing
site with a login form. This is codified as the *Trust Before
Credentials* principle.

The disabled shell may display **non-sensitive operational
information** that reinforces confidence without exposing protected
information or creating interaction opportunities.

### 9.1 What the pre-auth shell MAY display

| Signal | Where | Why it matters | Sensitivity |
|---|---|---|---|
| **System health posture** | StatusRail bottom chip · single dot | The operator knows the platform is alive | Public (nominal / degraded / down) |
| **Kill posture chip** | StatusRail bottom | The Factory's operational stance is public by design | Public |
| **Environment label** | StatusRail bottom (e.g. `prod` · `staging`) | Confirms which instance the operator is signing into | Public |
| **Current UTC time** | Header right side, mono | Anchors the operator in the Factory's time frame | Public |
| **Platform version** | Footer or user-menu-adjacent chip (`@v55`) | Signals actively-maintained system | Public |
| **6-chip StatusRail overview** | Footer | Same 6 chips shown post-auth · aggregate posture only | Public (posture, not detail) |
| **Ambient shimmer / heartbeat** | Header brand chip | Subtle sign of aliveness | Cosmetic |
| **Brand chip** (`Strategy Factory`) | Header left | Identity | Public |

### 9.2 What the pre-auth shell MUST NOT display

| Signal | Why forbidden |
|---|---|
| Approval counts (`● 4 approvals`) | Reveals workload / activity level |
| Master Bot activity chip | Reveals plan state |
| Worker states / division activity | Reveals internal operations |
| Timeline events | Reveals actor activity |
| User-specific data of any kind | Trivially reveals prior logins |
| Governance advisories | Sensitive; belongs post-auth |
| Feature flag states | Reveals internal configuration |
| Any numeric metric > posture aggregate | Bloomberg-adjacent leakage |
| Any strategy identifier | Absolutely not |
| Any prop firm name | Reveals commercial relationships |
| Any broker identifier | Reveals infrastructure |
| Any error trace / stack / correlation id | Security / operational risk |

**The bar:** if a signal *could theoretically be inferred by an
unauthenticated visitor to compromise security or reveal operational
intelligence*, it does not appear pre-auth.

### 9.3 Rendering rules for pre-auth signals

- **Every pre-auth chip renders at full opacity**, not at reduced
  opacity. The pre-auth shell is *disabled for interaction*, not
  *dimmed for aesthetics*. This is the mechanism of Trust Before
  Credentials — the signals must feel *authoritative*, not *ghosted*.
- **LeftRail modules render at 40% opacity with lock icons** — they
  are visible-but-clearly-not-yet-accessible. This shows the operator
  the shape of what's behind the door.
- **Chips are non-interactive** pre-auth. Hover reveals a subtle
  `--stroke-2` outline but no tooltip; click does nothing. Every chip
  has `aria-disabled="true"` + `pointer-events: none`.
- **Kill-posture chip** is the one exception: it retains a tooltip
  showing *"Kill posture is public information."* — reinforcing why
  it's visible.

### 9.4 Kill posture visibility (subsumed into §9.1)

Kill posture is public. It is visible even before auth per §9.1.

**Rules** (moved from prior §9):

- StatusRail shows kill-posture chip pre-auth and post-auth
  identically (§3.1).
- Danger ribbon does **not** fire pre-auth (no operator to alert yet;
  banner instead — §9.5).
- **Immediately post-auth**, if kill posture is armed, the danger
  ribbon appears in the landing-crossfade — the operator's first
  frame post-auth carries the ribbon.

### 9.5 Kill posture pre-auth banner (never a ribbon)

When kill posture is armed and no session exists, the login card
carries a *muted banner above the sign-in header* — informational,
never alarming:

```
┌────────────────────────────────┐
│  ● Kill posture is armed.       │  ← --sig-dormant tint · muted
│    Deliberate operational       │
│    freeze in effect.            │
│  ─────────────────────────────  │
│                                 │
│  Sign in                        │
│  ...                            │
└────────────────────────────────┘
```

Colour `--sig-dormant`, never `--sig-crit` — kill posture is a *state*,
not a *threat*. Post-auth, the same posture surfaces as a `--sig-crit`
danger ribbon because it demands active operator attention.

### 9.6 Why Trust Before Credentials matters

Every element of the pre-auth shell is a *silent promise* that this
is not a demo, not a marketing page, not a wrapper — this is the
same product the operator sees post-auth, showing them exactly what
it can show without leaking anything it shouldn't.

The operator who arrives at the door of an autonomous trading factory
should not first see a login form on a white background. They should
see the factory's *heartbeat* — the six-chip status rail, the UTC
clock, the environment label, the kill-posture state — all present,
all authoritative, all silent.

**Rule of Silent Confidence.** A pre-auth shell should be able to be
screenshotted and shared publicly with zero information leak, while
still communicating to the operator that they are approaching a live
system.

### 9.7 Anti-patterns

- ❌ Displaying approval counts, worker states, or Timeline events pre-auth.
- ❌ Rendering pre-auth chips at reduced opacity — they must feel
  authoritative.
- ❌ A "Welcome" heading anywhere on the login screen.
- ❌ Product marketing (feature callouts, hero imagery, testimonials).
- ❌ Any interactive element other than the login form itself.
- ❌ Cookie banner (internal tool exemption).
- ❌ "Latest news" or blog links.

---

## 10. Auth-state impact on Context Never Lost & State Memory

### 10.1 CNL through the auth boundary

**Preserved through session expiry recovery:**

- Mode (localStorage — survives)
- Advanced Lens (localStorage — survives)
- Density (localStorage — survives)
- URL query payload — captured as `?next=` and restored post-auth
- Facet Bar state (from URL) — restored
- Time-window chip (from URL) — restored
- Selected artefact (from URL) — restored
- Pinned Preview tray (sessionStorage — survives within-tab; cleared
  on tab close)

**Cleared on logout:**

- Selected artefact
- Facet Bar state
- Time-window chip
- Pinned Preview tray
- Scroll positions
- Evidence Drawer state

Mode / Advanced Lens / Density **persist** in localStorage — a returning
operator on the same browser sees their preferred posture.

### 10.2 State Memory through the auth boundary

**Preserved through session expiry recovery:**

- Scroll positions (sessionStorage — survives)
- Expanded panels (sessionStorage — survives)
- Drawer states (sessionStorage — survives)
- Column sort (sessionStorage — survives)
- Local layout (sessionStorage — survives)

**Cleared on logout:**

- All sessionStorage cleared.

**Rule of Continuity.** For session expiry recovery, the operator's
return should feel *seamless* — they should barely notice the auth
event happened. For logout, they should get a *clean desk* — the next
person to sit down starts fresh.

---

## 11. Failure paths — the taxonomy

| Path | Trigger | Landing | Copy |
|---|---|---|---|
| A1 wrong-credentials | Password / email mismatch | Login screen with inline error | *"Email or password is incorrect."* |
| A2 account-locked | Too many attempts | Login screen with lockout notice | *"Account is temporarily locked. Try again in 15 minutes or contact your admin."* |
| A3 backend-unreachable | Auth service down | Login screen with retry | *"Sign-in service is unavailable. Retrying in 8 s."* |
| A4 session-expired | 401 on any request | Overlay login on current surface | *"Your session expired. Sign in again to resume."* |
| A5 must-change-password | Backend flag | Post-auth mandatory-change screen | *"Your account requires a new password before you continue."* |
| A6 invalid-invite | Invite token expired | Login screen with contact-admin copy | *"This invitation is no longer valid. Contact your admin."* (Sprint 3+ invitation flow) |
| A7 network-loss-mid-session | Fetch fails mid-session | Toast + auto-retry | *"Connection lost. Retrying in 8 s."* |
| A8 kill-posture-on-arrival | Kill posture armed post-auth | Landing + danger ribbon | (per §9) |
| A9 idle-timeout | Sprint 3+ | — | (deferred) |
| A10 multi-tab-logout | Sprint 3+ | — | (deferred) |

---

## 12. Copy library (Auth Experience subset)

Locked at E2 approval; every specimen obeys D7 §22 cadence rules.

### 12.1 Login screen

| Element | Copy |
|---|---|
| Heading | *"Sign in"* |
| Email label | *"email"* |
| Password label | *"password"* |
| Primary button | *"Sign in →"* |
| Contact footer | *"If you don't have an account, contact your admin."* |
| Loading button | *"Signing in…"* |

### 12.2 Post-auth events (Timeline · Advanced-Lens only)

| Event | Copy |
|---|---|
| First-time login | *"Operator signed in for the first time."* |
| Return login | *"Operator signed in."* |
| Password changed | *"Operator changed their password."* |
| Session expired | *"Operator's session expired after 8 h."* |
| Re-auth after expiry | *"Operator re-authenticated after session expiry."* |
| Logout | *"Operator signed out."* |
| Mode switched | *"Operator switched to <mode> mode."* |

### 12.3 Error specimens (D7-shape)

- `auth-error-credentials` — *"Email or password is incorrect."*
- `auth-error-locked` — *"Account is temporarily locked."*
- `auth-error-service` — *"Sign-in service is unavailable."*
- `auth-info-expired` — *"Your session expired."*
- `auth-info-first-time` — *"Set a new password."*

### 12.4 User menu

| Element | Copy |
|---|---|
| Session header | *"Session"* |
| Signed-in-at | *"signed in HH:MM"* |
| Extends label | *"extends every action"* |
| Expiry | *"expires HH:MM or sooner"* |
| Switch-mode shortcut hint | *"⌘M · switch mode"* |
| Sign-out shortcut hint | *"⌘L · sign out"* |

---

## 13. Data contract (frontend expectation · Feature Freeze respected)

Auth composes over the **existing** `/api/auth/*` endpoints. No new
endpoints.

```ts
type Session = {
  user_id: string;
  email: string;
  modes: Array<'executive' | 'operations' | 'research' | 'developer'>;
  default_mode: 'executive' | 'operations' | 'research' | 'developer';
  must_change_password: boolean;
  issued_at: string;                       // ISO
  expires_at: string;                      // ISO (sliding)
  advanced?: {
    session_id: string;                    // "sess_ab12cd34..."
    issuer: string;                        // "auth.strategy-factory"
  };
};

type LoginRequest = {
  email: string;
  password: string;
};

type LoginResponse =
  | { ok: true; session: Session; next?: string }
  | { ok: false; code: 'credentials' | 'locked' | 'service' | 'must_change_password'; message: string };

type PasswordChangeRequest = {
  new_password: string;
  confirm_password: string;
};
```

**Adapter:** `services/auth.js` — normalises to the canonical
`Session` type. Consumed by workspace state store on auth events.

**Feature Freeze respected.** No new backend endpoints; existing
`/api/auth/login`, `/api/auth/logout`, `/api/auth/session`,
`/api/auth/change-password` all pre-exist per handoff.

---

## 14. Accessibility

- Login form: proper `<form>` semantics; labels associated with inputs
  via `for` / `id`.
- `autocomplete` attributes: `email` on email input; `current-password`
  on password.
- Error messages: `aria-live="polite"`; associated with input via
  `aria-describedby`.
- Focus management: focus lands on email on mount; on submit-with-
  errors, focus lands on first errored field.
- Screen-reader announcement on state changes:
  - login attempt → *"Signing in..."*
  - success → *"Signed in as admin@coinnike.com. Landing on Mission
    Control."*
  - failure → error copy verbatim
- Reduced-motion respect: Editorial crossfade → opacity fade only.
- Password field: SR announces *"password field, hidden"*; toggle-
  visibility optional (not in Sprint 1 scope; adds complexity for
  marginal benefit).
- `data-testid` on every interactive element:
  `login-email-input` · `login-password-input` · `login-submit-btn` ·
  `user-menu-btn` · `sign-out-btn` · `mode-switcher-btn` etc.

---

## 15. Mode-specific auth behaviour

The auth flow is **mode-agnostic** (auth is orthogonal to mode).
However, post-auth landing differs by claimed mode:

| Claimed mode | Landing (D6 §12) |
|---|---|
| Executive | `/c/briefing` (Sprint 3+ — falls back to `/c/mission` for Sprint 1) |
| Operations *(default)* | `/c/mission` |
| Research | `/c/research` (Sprint 3+ — falls back to `/c/mission` for Sprint 1) |
| Developer | ⌘K palette (developer group) then `/c/mission` |

**Sprint 1 note:** because `/c/briefing` and `/c/research` don't ship
until Sprint 3+, Sprint 1 Executive and Research users fall back to
Mission Control post-auth. The mode is still claimed; only the landing
adjusts.

---

## 16. Sprint 1 acceptance criteria

Auth experience ships only if:

- ✅ 18-item Design Principles Checklist confirmed (§0)
- ✅ Login screen renders per §3.1 layout with shell chrome persistent
- ✅ Login flow completes end-to-end against existing `/api/auth/login`
- ✅ Latency budget met (§3.2) — button responds within 300 ms; optimistic UI at 200 ms
- ✅ All error states (§11) authored and rendered
- ✅ Kill posture visible pre-auth (§9.4)
- ✅ Trust Before Credentials — pre-auth shell renders §9.1 signals; §9.2 signals confirmed absent
- ✅ Mandatory password change (§6.1) implemented when backend flag is set
- ✅ Session expiry recovery preserves CNL + State Memory (§10)
- ✅ Logout clears sessionStorage but preserves localStorage (§7.2)
- ✅ Mode switcher shows only assigned modes (§8.2)
- ✅ User menu shows session provenance (§4.2) with Advanced-Lens details
- ✅ Post-auth landing per §15
- ✅ A11y — axe-core zero violations on login screen
- ✅ Screen-reader announcements verified (§14)
- ✅ Reduced-motion — Editorial crossfade collapses to fade
- ✅ Copy library (§12) applied verbatim
- ✅ Decision Identity — session data byte-identical across modes
- ✅ `data-testid` on every interactive element
- ✅ No new backend endpoints (Feature Freeze verified)

---

## 17. What E2 does NOT include

- Self-signup UI.
- SSO / OAuth integration (Sprint 3+).
- 2FA / MFA (Sprint 3+).
- Password recovery UI (admin-mediated in Sprint 1).
- Session-idle timeout (Sprint 3+).
- Multi-tab logout synchronisation (Sprint 3+).
- Passwordless / magic-link (future enhancement).
- Persistent "remember me" checkbox (session policy is deterministic).
- Illustrations / marketing content on the login screen.
- Consent / cookie-banner UX (internal tool; not required).
- Terms-of-service acceptance flow (out of scope; separate legal
  workflow).

---

## 18. Next: E3 — First-Time User Journey

Per D8 §13.6 (operator-directed sequencing).

E3 will codify the *moment-zero* experience after successful auth
for a first-time operator:

- Empty Mission Control on first visit (what does a Factory that has
  never done anything for this operator show?)
- First-time navigation choice (which module first?)
- Onboarding without wizards — how the product teaches itself.
- Persona-specific first-time experience.
- First-time discovery of ⌘K, modes, Advanced Lens.
- The first successful action — a first-time operator's *"aha"*
  moment.

Expected timeline: 2 days.

---

*End of E2 — Authentication Experience.*

*All 18 checklist items confirmed. Auth codified as a gate that
feels like the rest of the house. Session-expiry recovery preserves
Context Never Lost + State Memory. Kill posture visible pre-auth.
Bible v2.1 · D6 modes · D7 State Template · Backend Feature Freeze all
respected.*

*Awaiting operator review before authoring E3.*
