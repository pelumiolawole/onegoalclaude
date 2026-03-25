# OneGoal Pro — Product Requirements Document (PRD)
# Version: 2.0 — Live Product Edition
# Date: March 25, 2026
# Owner: Pelumi Olawole, IIC Networks
# Status: MVP shipped. This PRD formalises what exists and defines what's next.

---

## 1. PRODUCT OVERVIEW

### 1.1 What It Is
OneGoal Pro is an identity-based goal transformation system. It helps people commit to the one goal that will genuinely change who they are — not just what they do. Unlike conventional goal-setting tools that track tasks, OneGoal Pro tracks identity evolution.

### 1.2 Core Philosophy
Most goal-setting fails because people set the wrong goal, or the right goal with the wrong framing. OneGoal Pro operates on three principles:
1. You don't have a focus problem. You have an identity problem.
2. Behaviour follows identity. Change who you are, and the actions follow.
3. One goal, pursued with full commitment, beats ten goals pursued with divided attention.

### 1.3 Tagline
**"One goal. Full commitment. No excuses."**

### 1.4 What Makes It Different
- The user does not enter their goal. They discover it through an AI-guided psychological interview.
- Progress is measured as identity transformation, not task completion rate.
- The AI coach knows who you are becoming — it has memory, context, and a consistent point of view.
- The product is built around a single constraint: one goal, indefinite horizon.

---

## 2. TARGET USERS

### 2.1 Primary Persona — The Committed Changer
- Age: 25–45
- Ambitious professional, solopreneur, or creative
- Has tried other apps and abandoned them
- Knows what they want to change but keeps failing to sustain it
- Motivated by identity and who they're becoming, not just productivity metrics
- Willing to pay for something that actually works

### 2.2 Secondary Persona — The Seeker
- Knows something needs to change but hasn't articulated what
- Looking for clarity, not just accountability
- The AI interview is specifically designed for this person

### 2.3 Who It Is Not For
- People who want a task manager with more features
- People who want social accountability feeds
- People who want to track multiple goals simultaneously

---

## 3. USER FLOWS

### 3.1 Discovery & Sign Up
```
Landing page
  → View pricing tiers (Free / Pro / Elite)
  → Click "Start" or "Sign up"
  → Sign up: email+password OR Google OAuth
  → Email verification sent
  → Verify email
  → Enter onboarding flow
```

### 3.2 Onboarding Flow (One-time)
```
Interview page
  → AI Discovery Interview (V2 — 3-phase psychological funnel)
     Phase 1: Find the tension
       "What's the one area of your life that, if nothing changes in the next
        12 months, you'll genuinely be disappointed in yourself?"
     Phase 2: Find the real goal
       Probe past attempts, obstacles, identity, what success looks like
     Phase 3: Crystallise
       AI names the goal — user corrects it
       "What would you call yourself — not what you've achieved, but who
        you've become — when this is done?" → identity anchor
  → Goal setup page (AI-synthesised refined_statement displayed, user confirms)
  → Strategy preview (identity profile summary)
  → Activate (triggers first task generation)
  → Dashboard
```

### 3.3 Daily Loop (Core Engagement)
```
Dashboard
  → View today's task (identity_anchor or micro_action type)
  → Complete task → Reflection modal → Submit reflection
  → Streak updates immediately
  → Transformation score updates
  → AI Coach tab available for guidance
  → Progress tab for weekly review + traits timeline
```

### 3.4 Billing & Upgrade Flow
```
Settings → Upgrade tab
  → View tier comparison
  → Select Pro ($4.99/mo) or Elite ($10.99/mo)
  → Stripe Checkout session created
  → Payment → Stripe webhook → subscriptions table updated
  → User redirected to billing/success
  → Plan upgrades immediately (quota enforcement updates)
```

### 3.5 Offboarding / Account Management
```
Settings
  → Export my data (GDPR — downloads JSON of all user data)
  → Delete account (soft delete → 30-day grace period → hard delete)
  → Cancel subscription → Stripe cancels at period end → status → "ended"
```

---

## 4. FEATURE SPECIFICATIONS

### 4.1 Authentication

#### Sign Up
- Fields: email, password (min 8 chars)
- Google OAuth option
- Email verification required before access to app
- On success: create user record, create identity_profile record, set onboarding_step = 1

#### Login
- Email+password or Google OAuth
- Returns JWT access token + refresh token
- Refresh token rotates on use

#### Email Verification
- Verification email sent on signup
- Resend verification option available
- Unverified users cannot access the app

#### Password Reset
- Forgot password → email with reset link
- Reset link expires in 1 hour
- New password requirements: min 8 chars

#### Session Management
- JWT expiry: 30 minutes
- Refresh token: 7 days
- Tab-switch auth persistence: implemented

---

### 4.2 AI Discovery Interview

**Engine:** `backend/ai/engines/interview.py`
**Prompt:** `backend/ai/prompts/system_prompts.py` → `INTERVIEW_SYSTEM_V2`

#### Rules
- One question at a time. Non-negotiable.
- Reflect before asking. Every response acknowledges what was said.
- Never announce phases to the user.
- 8–15 message exchanges typical.

#### Completion
- When interview is complete, AI returns structured JSON:
  ```json
  {
    "refined_statement": "string",
    "identity_anchor": "string",
    "core_values": ["string"],
    "self_reported_strengths": ["string"],
    "key_tension": "string",
    "motivation_style": "string"
  }
  ```
- This data populates the `goals` and `identity_profiles` tables.

#### Error States
- If user gives very short answers: probe deeper, don't proceed
- If connection drops mid-interview: resume from last message
- If OpenAI API fails: show error, allow retry

---

### 4.3 Dashboard

**Route:** `/dashboard`
**File:** `frontend/src/app/(app)/dashboard/page.tsx`

#### Components
- **Today's task card** — title, description, complete button
- **Streak counter** — days_active, current streak (updates real-time on completion)
- **Transformation score ring** — 0–100, visual arc
- **Traits panel** — key identity traits with timeline
- **Task history panel** — last 30 tasks, collapsible
  - Green tick = completed
  - Amber dash = skipped
  - Red X = missed (pending at day end)
- **Week grid** — 7-day completion view

#### Task Completion Flow
1. User taps complete
2. Reflection modal appears (optional but encouraged)
3. On submit/skip: task marked complete, streak increments, score recalculates
4. Dashboard refreshes

---

### 4.4 AI Coach

**Route:** `/coach`
**File:** `frontend/src/app/(app)/coach/page.tsx`
**Backend:** `backend/ai/engines/coach.py`, `backend/api/routers/coach.py`

#### V2 Features (shipped March 20)
- PMOS framework (Purpose, Momentum, Obstacles, Strategy)
- Psychological coaching frameworks
- Enhanced memory system with pgvector semantic retrieval
- Streaming responses (FastAPI StreamingResponse)
- Session memory: retrieves relevant past sessions as context

#### Quota Enforcement
| Tier | Daily coach messages |
|---|---|
| Free | 5 |
| Pro | Unlimited |
| Elite | Unlimited |

- QuotaBanner component shows remaining messages
- On quota hit: graceful message with upgrade prompt

#### Coach Personality (Coach PO)
- Warm but direct
- Identity-language fluent
- Challenges comfortable excuses
- Never generic — always references user's specific goal and identity anchor

---

### 4.5 Progress

**Route:** `/progress`
**File:** `frontend/src/app/(app)/progress/page.tsx`

#### Transformation Score
- 0–100 scale
- Calculated from: task completion rate, reflection depth, streak consistency, coach engagement
- Real-time triggers on task completion
- Score ring visual component

#### Traits Timeline
- Tracks identity traits over time
- Data source: `progress_metrics` table
- SWR key: `/progress/traits/timeline`

#### Weekly AI Review
- Generated by scheduler every Sunday
- AI summary of the week's progress, patterns, and next week focus
- Displayed as a card in Progress tab

---

### 4.6 Settings

**Route:** `/settings`
**File:** `frontend/src/app/(app)/settings/page.tsx`

#### Profile
- Avatar upload (Supabase Storage, avatars bucket)
- AI bio generation: "Who you're becoming" — generated once on first visit, never regenerated
- Display name

#### Subscription
- View current plan
- Upgrade button → `/settings/Upgrade`
- Cancel subscription
- View invoice history

#### Account
- Export my data (GDPR)
- Delete account

#### Share
- Invite a friend (native share sheet)
- AI-generated invite message

---

### 4.7 Billing

**Files:** `backend/api/routers/billing.py`, `backend/services/billing.py`
**Frontend:** `frontend/src/app/(app)/settings/subscription/page.tsx`, `/settings/Upgrade/page.tsx`

#### Tiers
| Tier | Name | Price | Stripe Price ID |
|---|---|---|---|
| free | The Spark | $0 | — |
| pro | The Forge | $4.99/month | [set in env] |
| elite | The Identity | $10.99/month | [set in env] |

#### Checkout Flow
1. User clicks upgrade
2. Frontend calls `POST /api/billing/checkout`
3. Backend creates Stripe Checkout session
4. User redirected to Stripe
5. Payment complete → Stripe sends `checkout.session.completed` webhook
6. Backend receives webhook → updates `subscriptions` table
7. User redirected to `/billing/success`

#### Webhook Events Handled
- `checkout.session.completed` → activate subscription
- `customer.subscription.updated` → update plan/status
- `customer.subscription.deleted` → set status to "ended"
- `invoice.payment_succeeded` → log invoice
- `invoice.payment_failed` → flag for retry/notification

#### Database Schema Required (PENDING MIGRATION)
```sql
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan VARCHAR(20) NOT NULL DEFAULT 'free', -- free, pro, elite
  status VARCHAR(20) NOT NULL DEFAULT 'active', -- active, ended
  stripe_customer_id VARCHAR(255),
  stripe_subscription_id VARCHAR(255),
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE invoices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stripe_invoice_id VARCHAR(255) NOT NULL,
  amount_paid INTEGER NOT NULL, -- in cents
  currency VARCHAR(3) DEFAULT 'usd',
  status VARCHAR(20) NOT NULL,
  invoice_pdf_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_stripe_customer ON subscriptions(stripe_customer_id);
CREATE INDEX idx_invoices_user_id ON invoices(user_id);
```

---

### 4.8 Notifications (PENDING BUILD)

#### Web Push
- Service worker registration on first app load
- Store `PushSubscription` token in `push_subscriptions` table
- Trigger: daily morning sweep in `scheduler.py`
- Message: "Your identity task for today is ready — [task title]"
- Library: `web-push` (npm) on backend

#### Email Notifications
- Infrastructure: already built in `services/email.py`
- Add to scheduler: daily task digest at user's morning time
- Template: task title + identity anchor phrase + CTA button to app
- Re-engagement email: if no login in 3 days → "You have tasks waiting"

#### Required DB Table
```sql
CREATE TABLE push_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, endpoint)
);
```

---

### 4.9 Admin

**File:** `backend/api/routers/admin.py`

- View safety-flagged content
- Review and action flags
- Bulk welcome email to existing users
- User list (internal use only)
- All admin endpoints require admin role in JWT

---

## 5. API SPECIFICATION

### 5.1 Base URL
Production: `https://api.onegoalpro.app/api`

### 5.2 Authentication
All protected endpoints require: `Authorization: Bearer <jwt_token>`

### 5.3 Endpoints

#### Auth
| Method | Path | Description |
|---|---|---|
| POST | /auth/signup | Create account |
| POST | /auth/login | Login, returns tokens |
| POST | /auth/logout | Invalidate session |
| POST | /auth/refresh | Refresh JWT |
| POST | /auth/verify-email | Verify with token |
| POST | /auth/resend-verification | Resend email |
| POST | /auth/forgot-password | Send reset email |
| POST | /auth/reset-password | Set new password |
| GET | /auth/google | Initiate Google OAuth |
| GET | /auth/callback | Google OAuth callback |

#### Onboarding
| Method | Path | Description |
|---|---|---|
| POST | /onboarding/interview | Send interview message, get AI response |
| POST | /onboarding/complete-interview | Submit completed interview data |
| POST | /onboarding/goal | Save goal from interview synthesis |
| POST | /onboarding/activate | Activate goal, trigger task generation |
| GET | /onboarding/status | Get current onboarding step |

#### Goals
| Method | Path | Description |
|---|---|---|
| GET | /goals | Get current goal |
| PUT | /goals | Update goal |
| GET | /goals/strategy | Get goal strategy |

#### Tasks
| Method | Path | Description |
|---|---|---|
| GET | /tasks/today | Get today's task |
| POST | /tasks/{id}/complete | Mark task complete |
| GET | /tasks/history | Last 30 tasks with status |
| GET | /tasks/{date} | Tasks for specific date (YYYY-MM-DD) |

#### Coach
| Method | Path | Description |
|---|---|---|
| POST | /coach/message | Send message, get streaming response |
| GET | /coach/sessions | List past sessions |
| GET | /coach/quota | Current quota usage |

#### Progress
| Method | Path | Description |
|---|---|---|
| GET | /progress/score | Current transformation score |
| GET | /progress/traits/timeline | Traits over time |
| GET | /progress/weekly-review | Latest weekly review |
| POST | /progress/refresh-score | Manually trigger score recalculation |

#### Reflections
| Method | Path | Description |
|---|---|---|
| POST | /reflections | Submit task reflection |
| GET | /reflections/history | Past reflections |
| GET | /reflections/weekly-review | AI weekly review |

#### Profile
| Method | Path | Description |
|---|---|---|
| GET | /profile | Get profile (triggers bio gen on first call) |
| POST | /profile/avatar | Upload avatar |
| POST | /profile/bio/generate | Generate bio (idempotent) |
| POST | /profile/share-message | Generate invite message |

#### Settings
| Method | Path | Description |
|---|---|---|
| GET | /settings | Get user settings |
| PUT | /settings | Update settings |
| GET | /settings/timezone | Get timezone |
| PUT | /settings/timezone | Set timezone |

#### Billing
| Method | Path | Description |
|---|---|---|
| POST | /billing/checkout | Create Stripe checkout session |
| GET | /billing/subscription | Get subscription status |
| POST | /billing/cancel | Cancel at period end |
| POST | /billing/resume | Resume cancelled subscription |
| GET | /billing/invoices | Invoice history |
| POST | /billing/webhook | Stripe webhook receiver |
| GET | /billing/verify-session | Verify checkout session success |

#### Admin
| Method | Path | Description |
|---|---|---|
| GET | /admin/flags | List safety flags |
| POST | /admin/flags/{id}/review | Mark flag reviewed |
| POST | /admin/welcome-email | Send welcome to all users |

---

## 6. DATABASE SCHEMA

### 6.1 Confirmed Existing Tables

#### users
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | VARCHAR UNIQUE | |
| hashed_password | VARCHAR | nullable (OAuth users) |
| is_verified | BOOLEAN | default false |
| is_active | BOOLEAN | default true |
| role | VARCHAR | user / admin |
| onboarding_step | INTEGER | 1–5 |
| timezone | VARCHAR | e.g. Europe/London |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

#### goals
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | |
| refined_statement | TEXT | AI-synthesised goal |
| identity_anchor | TEXT | "Who you become" |
| core_values | JSONB | |
| strategy | JSONB | |
| is_active | BOOLEAN | |
| created_at | TIMESTAMPTZ | |

#### identity_profiles
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | UNIQUE |
| transformation_score | INTEGER | 0–100 |
| streak | INTEGER | current streak |
| days_active | INTEGER | total active days |
| bio | TEXT | AI-generated |
| traits | JSONB | |
| strengths | JSONB | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

#### tasks
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | |
| title | TEXT | |
| description | TEXT | |
| task_type | VARCHAR | identity_anchor / micro_action |
| scheduled_date | DATE | |
| status | VARCHAR | pending / completed / skipped |
| completed_at | TIMESTAMPTZ | nullable |
| created_at | TIMESTAMPTZ | |

#### coaching_sessions
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | |
| messages | JSONB | full conversation |
| session_summary | TEXT | AI-generated |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

#### reflections
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | |
| task_id | UUID FK → tasks | |
| qa_pairs | JSONB | Q&A from reflection |
| depth_score | FLOAT | |
| created_at | TIMESTAMPTZ | |

#### progress_metrics
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | |
| date | DATE | |
| tasks_completed | INTEGER | |
| depth_score | FLOAT | NOT avg_depth_score |
| score_delta | FLOAT | |
| created_at | TIMESTAMPTZ | |

#### user_embeddings
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | |
| content | TEXT | source text |
| embedding | vector(1536) | OpenAI embedding |
| content_type | VARCHAR | session / reflection / goal |
| created_at | TIMESTAMPTZ | |

### 6.2 Pending Tables (must be created)
See Section 4.7 (billing) and Section 4.8 (notifications) for SQL.

---

## 7. SECURITY & PRIVACY

### 7.1 Authentication Security
- Passwords hashed with bcrypt (never stored plaintext)
- JWT tokens signed with RS256 or HS256 (config-dependent)
- Refresh tokens rotated on use
- OAuth state parameter validated to prevent CSRF

### 7.2 Data Privacy
- GDPR data export: returns all user data as JSON download
- Account deletion: soft delete → 30-day grace → hard delete cascade
- No user data sold or shared with third parties
- Stripe handles all payment data (PCI compliant)

### 7.3 API Security
- Rate limiting on all endpoints (middleware.py)
- CORS restricted to onegoalpro.app + localhost dev
- Admin endpoints require admin role claim in JWT
- Safety filter on all AI-generated content

### 7.4 Content Safety
- Safety filter (`ai/utils/safety_filter.py`) on coach responses
- Flagged content logged to admin review queue
- No harmful, discriminatory, or illegal content generated

---

## 8. ERROR HANDLING

### 8.1 Backend Error Responses
All errors return:
```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE_STRING"
}
```

| HTTP Code | Meaning |
|---|---|
| 400 | Bad request (validation error) |
| 401 | Unauthenticated |
| 403 | Forbidden (wrong role or tier) |
| 404 | Resource not found |
| 422 | Unprocessable entity |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

### 8.2 Frontend Error Handling
- Auth errors → redirect to login
- 429 on coach → show quota banner
- 500 errors → show "something went wrong, try again" toast
- Network offline → show offline banner
- Stripe checkout failure → return to upgrade page with error message

### 8.3 AI Failure States
- OpenAI API down → catch exception, return "Coach is unavailable right now" message
- Interview interrupted mid-flow → resume from last message on reload
- Task generation fails → retry next morning sweep, send fallback task if 3 days missed

---

## 9. ANALYTICS & TRACKING

### 9.1 Events to Track (pending PostHog setup)
| Event | Trigger |
|---|---|
| `signup_started` | Sign up page load |
| `signup_completed` | Account created |
| `interview_started` | First interview message |
| `interview_completed` | Interview data submitted |
| `goal_activated` | Activate button clicked |
| `task_completed` | Task marked done |
| `coach_message_sent` | Message sent to coach |
| `upgrade_clicked` | Upgrade button clicked |
| `subscription_created` | Stripe webhook: checkout complete |
| `subscription_cancelled` | Cancellation confirmed |

### 9.2 Key Metrics Dashboard (internal)
- Daily active users
- Onboarding completion rate (interview → activation)
- Daily task completion rate
- Coach sessions per user per week
- Streak distribution
- Conversion: free → pro
- Churn rate

---

## 10. MONETISATION

### 10.1 Tiers
| Tier | Price | Coach | Re-interview | Notes |
|---|---|---|---|---|
| Free (The Spark) | $0 | 5/day | No | Full onboarding, 3 tasks/day |
| Pro (The Forge) | $4.99/mo | Unlimited | No | Full access |
| Elite (The Identity) | $10.99/mo | Unlimited | Yes | Re-interview anytime |

### 10.2 Revenue Model
- Monthly recurring subscriptions via Stripe
- No annual plan yet (post-MVP consideration)
- No ads. No data monetisation. Clean product.

### 10.3 Growth Target
- Month 1: 11 → 50 users (word of mouth + notifications live)
- Month 2: 50 → 200 users (first paid marketing test)
- Month 3: first 10 paying users (conversion from free base)

---

## 11. ROADMAP

### Phase 1 — MVP Close (Weeks 1–4, by April 22 2026)
1. Remove .claude/worktrees/ from repo
2. Billing DB migration (subscriptions + invoices)
3. Stripe webhook live test
4. Web push notifications
5. Email notifications (daily task + re-engagement)
6. Mobile QA pass
7. Verify posthog.ts not in live imports

### Phase 2 — Growth (Months 2–3)
1. Grow to 50+ real users
2. PostHog analytics (properly)
3. Re-interview flow (Elite)
4. A/B test onboarding length
5. Referral mechanics
6. Apple OAuth
7. Weekly email digest

### Phase 3 — Mobile App (Month 3)
1. Capacitor wrapper on existing Next.js codebase
2. iOS + Android builds
3. App Store + Play Store submission
4. Native push notifications

---

## 12. AI AGENT SPECIFICATIONS

### 12.1 PM Agent
**Purpose:** Maintains product direction, updates documentation, manages sprint
**Invocation:** "Ask the PM agent to..."
**Capabilities:**
- Update TODO.md based on session outcomes
- Write new tickets for discovered issues
- Prioritise backlog on request
- Summarise product status for external stakeholders
- Draft product announcements

**System prompt skeleton:**
```
You are the Product Manager for OneGoal Pro, an identity transformation app.
You maintain the PRD, TODO.md, and sprint backlog.
You understand the full product context from CLAUDE.md.
You are organised, direct, and always prioritise by user impact.
When asked to update TODO.md, output the complete updated file.
```

### 12.2 Marketing Agent
**Purpose:** Content, copy, growth, brand voice
**Invocation:** "Ask the marketing agent to..."
**Capabilities:**
- Write social posts (LinkedIn, Instagram, Twitter/X)
- Write email sequences (onboarding, re-engagement, upgrade nudge)
- Write landing page copy
- Generate ad concepts
- Write in Pelumi's author voice when needed
- Produce content for IIC Networks and author brand

**Brand voice:** Identity-driven, direct, no corporate fluff, faith-informed when relevant, practical above all.

**System prompt skeleton:**
```
You are the Marketing Agent for OneGoal Pro and IIC Networks.
You write in the voice of Pelumi Olawole — a British-Nigerian coach, author, and founder.
Tone: direct, warm, identity-driven, occasionally sharp, always honest.
You understand the product deeply: it is an identity transformation system, not a task manager.
Always reference identity language: "who you're becoming", "the version of you that has already done this."
Never use generic productivity language.
```

### 12.3 QA Agent
**Purpose:** Code review, bug detection, test cases
**Invocation:** "Ask the QA agent to review..."
**Capabilities:**
- Review code for asyncpg syntax issues (the most common bug class)
- Check route ordering (named before catch-all)
- Verify error handling on critical paths
- Write test cases for new features
- Pre-deployment checklist

**System prompt skeleton:**
```
You are the QA Agent for OneGoal Pro.
You are paranoid about bugs. You assume every line of code is wrong until proven otherwise.
You know the common bug patterns in this codebase:
1. asyncpg cannot parse ::vector, ::jsonb, ::text[] cast syntax with named params
2. FastAPI named routes must come before catch-all routes
3. Supabase Storage must use supabase-py, not raw httpx
4. Streak updates must be immediate, not deferred
5. JSON serialisation must use json.dumps(), not str()
Before approving any code, check for all of the above.
```

### 12.4 Support Agent
**Purpose:** User-facing communication, feedback handling
**Invocation:** "Ask the support agent to..."
**Capabilities:**
- Draft responses to user feedback
- Respond to bug reports from users
- Write FAQ content
- Escalate genuine bugs to PM agent
- Draft re-engagement messages for inactive users

**System prompt skeleton:**
```
You are the Support Agent for OneGoal Pro.
You respond to users with warmth, clarity, and identity-language fluency.
You know the product deeply. You never make up features that don't exist.
When a user reports a bug, you acknowledge it, explain what happened simply, and tell them what's being done.
You write in Pelumi's voice but slightly softer — you are the human face of the product.
```

---

*End of PRD v2.0*
*Next review: after Phase 1 MVP close (April 22, 2026)*