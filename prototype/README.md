# Strategy Factory — Interactive Prototype

**Design-validation instrument** per D8 §13.7. Throw-away discipline — matches production stack (React + Vite + Zustand + Framer + Tailwind + Lucide) but is not production code.

## Governed by

- `../memory/FRONTEND_DESIGN_BIBLE_V2_1.md` (canonical)
- `../memory/D0` – `../memory/D8` (design system)
- `../memory/E1` – `../memory/E5` (experience series)
- `../memory/P0_PROTOTYPE_BLUEPRINT.md` (this prototype's contract)

## Six evaluation dimensions

Every session validates: Discoverability · Navigation Predictability · Cognitive Load · Interaction Rhythm · Operator Trust · Product Identity. See P0 §2.

## Build phases (P0 §8)

- ✅ **Phase 1 · Foundation** — tokens · state store · AppShell scaffold · StateTemplate + Chip primitives · routing
- ⏳ Phase 2 · Remaining 13 primitives (D8 §4.P)
- ⏳ Phase 3 · Login + Trust Before Credentials
- ⏳ Phase 4 · Core surfaces (Mission Control · Timeline · Approvals · Master Bot skeleton · Explorer · Passport)
- ⏳ Phase 5 · Cross-module wiring · Rule of Predictable Return
- ⏳ Phase 6 · Polish · Fixture Debug Panel · walk-through prep

## Run locally

```
cd /app/prototype
yarn install
yarn dev
```

## Do NOT

- Copy this code into `/app/frontend/`.
- Add production tooling.
- Add tests here (Sprint 1's job).
- Introduce new tokens, primitives, or design rules — refinements land as formal D/E-series addenda (P0 §10).
