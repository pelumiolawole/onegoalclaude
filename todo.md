# OneGoal Pro — TODO
# Updated: March 25, 2026 (end of session)
# This is the single source of sprint truth. Update it at the end of every session.

---

## CURRENT SPRINT: MVP CLOSE
Target completion: April 22, 2026 (4 weeks from March 25)
Goal: Every feature that exists in code must actually work end-to-end.

---

## 🔴 BLOCKERS — Do these first

- [ ] **Stripe webhook live test**
  - Complete a real test payment using a test account (not your main account)
  - Confirm Stripe webhook fires and `subscriptions` table updates correctly
  - Check Railway logs for `subscription_activated` log line
  - Verify user's plan shows as Pro/Elite in settings after payment

- [ ] **Fix ENVIROMENT typo in Railway**
  - Railway → Variables → rename `ENVIROMENT` to `ENVIRONMENT`
  - Redeploy to pick up the fix
  - Verify app is running in production mode

---

## 🟡 HIGH PRIORITY — MVP incomplete without these

- [ ] **Web push notifications**
  - `notification_queue` and `push_subscriptions` tables already exist in Supabase
  - Library: `web-push` npm package on backend
  - Steps: service worker on frontend → store push token in push_subscriptions → wire scheduler to send via notification_queue
  - Trigger: daily at user's local morning time (timezone already tracked)
  - Message: "Your identity task for today is ready — [task title]"

- [ ] **Email notifications — daily task reminder**
  - Email infrastructure already built in `services/email.py` via Resend
  - Add to morning sweep in `scheduler.py`: send daily task email
  - Template: task title + identity anchor + CTA button
  - Re-engagement: if no login in 3 days → "You have tasks waiting"

- [ ] **Verify posthog.ts not imported in live frontend**
  ```bash
  grep -r "posthog" frontend/src --include="*.ts" --include="*.tsx"
  ```
  If anything returns, remove the import.

- [ ] **Verify PASSWORD_RESET_FRONTEND_URL in Railway**
  - Should be `https://onegoalpro.app` not old Vercel URL
  - Check Railway → Variables → eye icon on that var

- [ ] **Mobile QA pass**
  - Test every screen on actual mobile
  - Priority: dashboard, interview, coach, settings, upgrade flow
  - Fix any layout breaks, overflow, tap target issues

---

## 🟢 NEXT UP

- [ ] **Identify and engage 4 unknown organic users**
  - Emails: busayo@simpletest.ai, awodipog@gmail.com, abimbolaobaje@gmail.com, adigsmanuel@gmail.com
  - Check Railway logs for their last activity
  - Send personal outreach asking for feedback

- [ ] **Verify billing/success page calls verify-session correctly**
  - `billing/success/page.tsx` calls `api.billing.verifySession?.()` — check it's hitting the new endpoint
  - Run: `grep -n "verifySession\|verify-session" frontend/src/app/\(app\)/billing/success/page.tsx`

- [ ] **Coach session review**
  - All 11 users had exactly 1 coach session and never returned
  - Test a full coach conversation manually with a test account
  - Confirm Coach V2 (PMOS upgrade, March 20) is responding correctly

- [ ] **Password reset end-to-end test**
  - Test full forgot-password → email → reset-password flow
  - Confirm email arrives from coach@pelumiolawole.com (or Resend sender)

- [ ] **Scoring verification**
  - Run: `SELECT user_id, transformation_score FROM identity_profiles`
  - Confirm all 11 users have a non-null score

---

## 📋 PHASE 2 BACKLOG (Month 2–3)

- [ ] Grow to 50+ real users (referral push after notifications live)
- [ ] Re-interview flow for Elite tier
- [ ] Capacitor wrapper for iOS/Android
- [ ] PostHog analytics (set up properly, not dead code version)
- [ ] A/B test onboarding completion rate
- [ ] 2-person accountability partnerships
- [ ] Apple OAuth
- [ ] Weekly email digest (progress summary)
- [ ] Annual billing option (already in Stripe, not shown in upgrade page)

---

## 📋 PHASE 3 BACKLOG (Month 3 — Mobile)

- [ ] iOS App Store submission
- [ ] Google Play Store submission
- [ ] Native push notifications (APNs + FCM)
- [ ] Mobile-specific UI polish pass
- [ ] App Store screenshots and listing

---

## ✅ COMPLETED

- [x] Core user journey (signup → interview → goal → dashboard)
- [x] AI Interview Engine V2 (psychological funnel)
- [x] AI Coach V2 (PMOS + psychological frameworks + session memory)
- [x] Transformation scoring system (repaired March 20)
- [x] Tier-based quota enforcement
- [x] Google OAuth
- [x] Email verification + password reset
- [x] Avatar upload
- [x] AI bio generation
- [x] Streak real-time updates
- [x] Task history panel (30 tasks, colour-coded)
- [x] Domain setup (onegoalpro.app)
- [x] GDPR data export + account deletion
- [x] Admin endpoints
- [x] 10 critical bugs resolved
- [x] CLAUDE.md, TODO.md, PRD v2, agent files created (March 25)
- [x] Codebase audit completed (docs/CODEBASE_AUDIT.md)
- [x] .claude/worktrees/ removed from repo
- [x] Billing DB migration — subscriptions, invoices, push_subscriptions, user_embeddings, coaching_sessions tables created
- [x] All 11 users seeded with free tier subscription records
- [x] FRONTEND_URL hardcode fixed — now reads from Railway env var
- [x] Stripe billing router — verify-session endpoint added
- [x] Billing service — webhook errors now logged (no more silent failures)
- [x] Billing service — dual-write to subscriptions table on all webhook events
- [x] Upgrade page routing fixed — renamed Upgrade → upgrade (case-sensitive Vercel fix)
- [x] FRONTEND_URL Railway env var set to https://onegoalpro.app
- [x] subscriptions table unique constraint added (user_id)

---

## SESSION LOG

| Date | What was done | Who |
|---|---|---|
| 2026-03-25 | Created CLAUDE.md, TODO.md, PRD v2, agent files, codebase audit | Claude |
| 2026-03-25 | Created 5 missing DB tables, fixed billing code, fixed routing, confirmed 11 users, £3.74 MRR | Claude + Pelumi |

---

*Update this file at the end of every session.*
*Move completed items to ✅ COMPLETED. Add new items as discovered.*