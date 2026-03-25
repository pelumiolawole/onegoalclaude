# OneGoal Pro — Master Claude Skill File
# Version: 1.1 | Last updated: March 25, 2026
# READ THIS ENTIRE FILE BEFORE DOING ANYTHING ELSE IN THIS SESSION

---

## WHO YOU ARE WORKING WITH

**Name:** Pelumi Olawole
**Role:** Founder, IIC Networks (Influence, Impact, Change) | Author | Coach | Day job: E.ON Next (UK)
**Book:** *Petty Little Things: 50 Habits Quietly Ruining Your Life and How to Fix Them*
**Working environment:** Windows, VS Code, Git Bash
**Skill level:** Rebuilding development skills — needs explicit step-by-step terminal instructions
**Deployment workflow:** Local edits → push to GitHub → auto-deploy (Railway ~10–15 min, Vercel ~2 min)
**Testing:** Primarily on mobile. No browser DevTools available. Railway logs are primary debug tool.
**File delivery preference:** Complete corrected files ready to copy-paste. No partial diffs unless trivial.
**Communication preference:** Plain English explanation of what's wrong BEFORE any code.

---

## WHAT WE ARE BUILDING

**Product:** OneGoal Pro
**Tagline:** One goal. Full commitment. No excuses.
**Core idea:** Identity-based goal transformation. Not what to do — who to become.
**Live URL:** https://onegoalpro.app
**API URL:** https://api.onegoalpro.app
**GitHub:** https://github.com/pelumiolawole/onegoalclaude
**Stage:** MVP — deployed, 11 registered users (3 real: wife, engineer, friend. 4 unknown organic signups. 4 test accounts.)
**Revenue:** 1 active paying subscriber on The Forge. MRR: £3.74 as of March 25, 2026.

---

## TECH STACK — PRODUCTION

| Layer | Technology | Provider | URL |
|---|---|---|---|
| Frontend | Next.js 15 (React 19) | Vercel | onegoalpro.app |
| Backend | FastAPI (Python) | Railway | api.onegoalpro.app |
| Database | Supabase (PostgreSQL + pgvector) | Supabase | project: one-goal-v2 |
| Cache | Redis | Railway | internal |
| AI | OpenAI GPT-4o-mini | OpenAI | — |
| Storage | Supabase Storage (avatars bucket) | Supabase | — |
| Auth | JWT + Google OAuth | Supabase Auth | — |
| Email | Resend (core/email.py + services/email.py) | Resend | — |
| Payments | Stripe — LIVE, 1 active subscriber | Stripe | — |
| Scheduler | APScheduler | Railway (in-process) | — |
| Domain | Cloudflare Registrar | Cloudflare | — |
| Error tracking | Sentry — live in frontend and backend | Sentry | — |

---

## REPOSITORY STRUCTURE

```
onegoalclaude/
├── backend/
│   ├── ai/
│   │   ├── base.py
│   │   ├── engines/
│   │   │   ├── coach.py               # AI Coach V2 — PMOS + psychological frameworks
│   │   │   ├── goal_decomposer.py
│   │   │   ├── interview.py           # Discovery interview engine V2
│   │   │   ├── profile_updater.py
│   │   │   ├── reflection_analyzer.py
│   │   │   └── task_generator.py
│   │   ├── memory/
│   │   │   ├── context_builder.py
│   │   │   └── retrieval.py           # pgvector semantic retrieval
│   │   ├── prompts/
│   │   │   └── system_prompts.py      # All AI prompts — centralised and versioned
│   │   └── utils/
│   │       ├── cost_tracker.py
│   │       └── safety_filter.py
│   ├── api/
│   │   ├── dependencies/auth.py
│   │   ├── routers/
│   │   │   ├── admin.py
│   │   │   ├── auth.py
│   │   │   ├── billing.py             # Stripe — LIVE. FRONTEND_URL from env var.
│   │   │   ├── coach.py
│   │   │   ├── goals.py
│   │   │   ├── onboarding.py
│   │   │   ├── profile.py
│   │   │   ├── progress.py
│   │   │   ├── reflections.py
│   │   │   ├── settings.py
│   │   │   └── tasks.py
│   │   └── schemas/
│   │       ├── auth.py
│   │       └── core.py
│   ├── core/
│   │   ├── cache.py
│   │   ├── config.py                  # All env vars live here
│   │   ├── database.py
│   │   ├── email.py
│   │   ├── middleware.py
│   │   └── security.py
│   ├── db/models/
│   │   ├── __init__.py
│   │   ├── goal.py
│   │   ├── identity_profile.py
│   │   ├── task.py
│   │   └── user.py
│   ├── services/
│   │   ├── analytics.py
│   │   ├── billing.py                 # Dual-writes to users + subscriptions tables
│   │   ├── data_export.py
│   │   ├── email.py
│   │   ├── scheduler.py
│   │   └── scoring.py
│   └── main.py
├── frontend/
│   ├── src/app/
│   │   ├── (app)/
│   │   │   ├── billing/cancel/
│   │   │   ├── billing/success/
│   │   │   ├── coach/
│   │   │   ├── dashboard/
│   │   │   ├── goal/
│   │   │   ├── progress/
│   │   │   └── settings/
│   │   │       ├── upgrade/           # LOWERCASE — was Upgrade, renamed March 25
│   │   │       └── subscription/
│   │   ├── (auth)/
│   │   ├── (onboarding)/
│   │   ├── auth/callback/
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── src/components/
│   ├── src/hooks/
│   ├── src/lib/
│   │   ├── api.ts                     # ALL backend calls go through here
│   │   ├── posthog.ts                 # ⚠️ EXISTS — verify not imported anywhere
│   │   └── utils.ts
│   └── src/stores/auth.ts
├── dead code/                         # Do not touch or import from here
├── docs/
│   ├── PRD_v2.md
│   ├── agents/
│   │   ├── PM_AGENT.md
│   │   ├── MARKETING_AGENT.md
│   │   ├── QA_AGENT.md
│   │   └── SUPPORT_AGENT.md
│   └── commit_history.txt
├── CLAUDE.md                          # THIS FILE
└── TODO.md                            # Current sprint tasks
```

---

## WHAT IS FULLY BUILT AND WORKING

### Core user journey (end-to-end)
Landing page → Sign up / Login (email + Google OAuth) → AI Discovery Interview (V2) → Goal synthesis → Strategy preview → Activation → Dashboard → Daily tasks → AI Coach → Progress → Settings → Upgrade → Stripe checkout → Billing success

### Backend systems (all live)
- JWT auth with token refresh
- Google OAuth via Supabase
- Email verification + password reset
- AI Interview Engine V2 (psychological funnel)
- Goal synthesis from interview
- Daily task generation (APScheduler, 4am sweep + guardrail)
- AI Coach V2 with PMOS + psychological frameworks + session memory (pgvector)
- Transformation scoring system
- Traits timeline + weekly review generation
- Reflection submission + analysis
- Avatar upload (Supabase Storage)
- AI bio generation (once on first Settings visit)
- Invite/share flow
- Tier-based quota enforcement on AI coach
- GDPR data export + account deletion
- Admin endpoints + safety flag review
- Email service via Resend
- Stripe billing — checkout, webhooks, cancel, resume, invoices, verify-session

### Billing — what's live as of March 25, 2026
- Stripe checkout working end-to-end
- Webhook handlers dual-write to `users` AND `subscriptions` tables
- FRONTEND_URL reads from Railway env var (set to https://onegoalpro.app)
- `/billing/verify-session` endpoint added
- Upgrade page routing fixed (lowercase `/settings/upgrade`)
- 1 active subscriber, MRR £3.74

---

## CRITICAL KNOWN ISSUES — CHECK BEFORE EVERY SESSION

### 1. PUSH NOTIFICATIONS — NOT BUILT (HIGHEST PRIORITY)
No web push or email notification system exists.
All 11 users tried the coach once and never returned.
Two users have 12–17 missed tasks — backlog intervention triggers but nothing reaches them.
`notification_queue` and `push_subscriptions` tables exist in Supabase. Just needs wiring.

### 2. RAILWAY ENV VAR TYPO
`ENVIROMENT` is misspelled in Railway variables (should be `ENVIRONMENT`).
App may be running in development mode. Fix in Railway → Variables.

### 3. PASSWORD_RESET_FRONTEND_URL
Verify this Railway var is `https://onegoalpro.app` not the old Vercel URL.

### 4. POSTHOG IN LIVE FRONTEND
`frontend/src/lib/posthog.ts` exists. Verify not imported anywhere:
```bash
grep -r "posthog" frontend/src --include="*.ts" --include="*.tsx"
```

### 5. STRIPE WEBHOOK — NEEDS LIVE TEST
Billing code is deployed but a real end-to-end webhook test hasn't been confirmed.
Test: use a test account to complete a real Stripe checkout, confirm subscriptions table updates.

### 6. 4 UNKNOWN ORGANIC USERS
busayo@simpletest.ai, awodipog@gmail.com, abimbolaobaje@gmail.com, adigsmanuel@gmail.com
These people found the app organically. Identify and engage them.

---

## ENGINEERING RULES — NEVER VIOLATE THESE

1. **Supabase Storage** — always use `supabase-py` client, never raw `httpx` calls
2. **asyncpg vector syntax** — never use `:param::vector`. Always inline in f-strings or use `CAST(:param AS vector)`
3. **asyncpg type casts** — avoid `::jsonb`, `::text[]` with named params. Use `CAST()` syntax
4. **FastAPI route ordering** — named routes MUST be defined BEFORE catch-all routes (`/{date}`)
5. **Streak updates** — always update immediately on user action, never defer to scheduler
6. **Task queries** — never filter on specific `task_type` values unless deliberately excluding
7. **JSON serialisation** — always `json.dumps()`, never `str()` on structured data
8. **Environment variables** — never hardcode. All config lives in `backend/core/config.py`
9. **File delivery** — always deliver complete files. Pelumi deploys by replacing whole files
10. **No partial diffs** unless the change is a single clearly-identified line
11. **Billing dual-write** — webhook handlers must write to BOTH `users` AND `subscriptions` tables
12. **Frontend routing** — all Next.js folder names must be lowercase (Vercel is case-sensitive on Linux)

---

## DEPLOYMENT PROCEDURE

### Backend (Railway)
```bash
git add -A
git commit -m "your message"
git push origin main
# Railway auto-deploys ~10–15 min. Monitor: Railway → Deployments → View logs
```

### Frontend (Vercel)
```bash
# Same git push — Vercel auto-deploys ~2 min
```

### Environment variables
- Backend: Railway → Service → Variables
- Frontend: Vercel → Project → Settings → Environment Variables
- Never commit `.env` files

---

## MONETISATION TIERS

| Tier | Name | Monthly | Annual | Coach quota |
|---|---|---|---|---|
| Free | The Spark | $0 | — | 5 messages/day |
| Pro | The Forge | $4.99 | $47.88 | Unlimited |
| Elite | The Identity | $10.99 | $107.88 | Unlimited + re-interview |

---

## DATABASE — ALL CONFIRMED EXISTING TABLES

### Core
- `users` — includes subscription_plan, stripe_customer_id, stripe_subscription_id columns
- `goals` — refined_statement (not title), identity_anchor
- `identity_profiles` — transformation_score, streak, days_active, bio
- `daily_tasks` — task_type: identity_anchor / micro_action
- `coaching_sessions` — messages JSONB, session_summary
- `reflections` — qa_pairs JSONB, depth_score (NOT avg_depth_score)
- `progress_metrics` — depth_score column
- `user_embeddings` — vector(1536) embeddings for coach memory

### Billing (created March 25, 2026)
- `subscriptions` — unique constraint on user_id. All 11 users seeded as 'free'.
- `invoices` — payment history

### Notifications (tables exist, sender not built)
- `notification_queue` — channel, scheduled_at, sent_at, opened_at, cancelled_at
- `push_subscriptions` — endpoint, p256dh, auth tokens

### Analytics / AI (extensive — created by earlier migrations)
- `ai_coach_messages`, `ai_coach_sessions`, `ai_interactions`, `ai_safety_flags`
- `behavioral_patterns`, `behavioral_snapshots`, `coach_interventions`
- `coach_moments`, `coach_patterns`, `coach_safety_flags`, `engagement_events`
- `identity_traits`, `milestones`, `objectives`, `onboarding_interview_state`
- `trait_progress_summary`, `weekly_reviews`, `users_needing_intervention` (view)
- `user_dashboard` (view), `data_processing_consent`, `deletion_requests`
- `integration_configs`, `system_config`

---

## AI SYSTEMS

### Interview Engine V2
3-phase psychological funnel — phases never announced to user:
1. Find the tension
2. Find the real goal
3. Crystallise identity anchor

### Coach V2 (PMOS + Psychological Frameworks)
Upgraded March 20. Session memory via pgvector. Streaming. Quota-enforced.

### Task Types
- `identity_anchor` — who you are becoming
- `micro_action` — small concrete action aligned to identity

---

## SESSION OPERATING PROCEDURE

**Start of every session:**
1. Read this file completely
2. Read `TODO.md` for current sprint focus
3. Ask "What are we working on today?" if TODO is ambiguous
4. Do not start coding until the task is clear

**During session:**
- Plain English explanation before code
- Complete files only — no partial diffs
- Check asyncpg gotchas, route ordering, type casts before delivering
- Update `TODO.md` after each completed task

**Debugging order:** Railway logs → Supabase queries → manual logic trace → fix root cause

---

## AI AGENTS ROSTER

All agent files live in `docs/agents/`. To use: open new Claude conversation, paste agent file contents, give task.

| Agent | Trigger | File |
|---|---|---|
| PM Agent | "Ask the PM agent" | docs/agents/PM_AGENT.md |
| Marketing Agent | "Ask the marketing agent" | docs/agents/MARKETING_AGENT.md |
| QA Agent | "Ask the QA agent" | docs/agents/QA_AGENT.md |
| Support Agent | "Ask the support agent" | docs/agents/SUPPORT_AGENT.md |

---

## OTHER PELUMI BRANDS

**IIC Networks** — Influence, Impact, Change. Coaching, speaking, leadership.
Voice: Authoritative, practical, faith-informed, African professional context.

**Author Brand (@PelumiOlawole)** — Book: *Petty Little Things*.
Voice: Conversational, honest, sometimes sharp, always constructive.
Platform: LinkedIn + Instagram.

---

## HOW TO UPDATE THIS FILE

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — [what changed]"
git push origin main
```
Then paste updated contents into this Claude Project's custom instructions.

---

*This file is the single source of truth for all Claude sessions on OneGoal Pro.*
*If something contradicts this file, this file wins unless Pelumi says otherwise.*