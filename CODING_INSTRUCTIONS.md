# OneGoal Pro — Coding Instructions for Claude
# Version: 1.0 | Created: March 27, 2026
# ADD THIS FILE TO THE PROJECT ROOT. Reference it at the start of every session.

---

## HOW EDITS ARE MADE

### Rule 1: Surgical edits only
When fixing a bug or adding a feature, change ONLY the affected lines or blocks.
Do not rewrite, restructure, or clean up any part of the file that is not directly
related to the current task. If the task is to fix a bug in `_save_message`, touch
only `_save_message`. Nothing else.

### Rule 2: Never recreate files from scratch unless explicitly asked
Recreating a file from scratch is only acceptable when:
- The user explicitly says "rewrite this file"
- The file is brand new and does not exist yet

For all other cases: use `str_replace` to make targeted changes to the existing file.

### Rule 3: When a full file must be delivered, verify it against the original first
If a full file delivery is unavoidable, diff it mentally against the original before
delivering. Call out any lines that were removed or changed beyond the stated scope.
Never silently drop existing fixes.

### Rule 4: When the user reports a regression, own it immediately
If a previously working fix is gone after an edit session, acknowledge it, identify
the cause, and re-apply the fix in the next output. Do not ask the user to re-explain
what the fix was — it should be in this file or in session memory.

---

## PERMANENT FIXES — NEVER REMOVE THESE

These are fixes that have been applied and must survive every future edit to their
respective files. When touching these files for any reason, verify these lines are
still present before delivering output.

### frontend/src/app/(app)/coach/page.tsx

**Fix: Mobile nav clearance**
The outermost div must always have `pb-16 md:pb-0` to prevent content hiding under
the fixed mobile bottom navigation bar.

```tsx
// CORRECT — always keep pb-16 md:pb-0
<div className="flex flex-col h-screen max-h-screen pb-16 md:pb-0">

// WRONG — missing the padding
<div className="flex flex-col h-screen max-h-screen">
```

**Fix: Mobile zoom prevention**
The TextareaAutosize input must use `text-base` (16px), NOT `text-sm` (14px).
Safari zooms the page on focus when input font size is below 16px.

```tsx
// CORRECT
className="flex-1 bg-transparent text-[#E8E2DC] placeholder:text-[#3D3630] text-base ..."

// WRONG — causes zoom on mobile
className="flex-1 bg-transparent text-[#E8E2DC] placeholder:text-[#3D3630] text-sm ..."
```

**Fix: SSE token space preservation**
`line.slice(6)` must NOT be followed by `.trim()`. Trimming strips the leading
space that OpenAI prepends to tokens, causing words to run together.

```tsx
// CORRECT
const data = line.slice(6)

// WRONG — causes "wordsruntogether" in coach responses
const data = line.slice(6).trim()
```

### frontend/src/app/(app)/layout.tsx

**Fix: Mobile nav fixed positioning**
The bottom nav must be `fixed bottom-0 left-0 right-0 z-50`.
The main content wrapper must have `pb-16 md:pb-0`.

### frontend/src/app/(app)/goal/page.tsx

**Fix: Mobile nav clearance**
Outermost div must include `pb-24 md:pb-8`.

```tsx
// CORRECT
className="p-6 md:p-8 pb-24 md:pb-8 max-w-3xl mx-auto space-y-5"
// WRONG
className="p-6 md:p-8 max-w-3xl mx-auto space-y-5"
```

### frontend/src/app/(app)/progress/page.tsx

**Fix: Mobile nav clearance**
Outermost div must include `pb-24 md:pb-8`.

```tsx
// CORRECT
className="p-6 md:p-8 pb-24 md:pb-8 max-w-3xl mx-auto space-y-6"
// WRONG
className="p-6 md:p-8 max-w-3xl mx-auto space-y-6"
```

### frontend/src/app/(app)/settings/page.tsx

**Fix: Mobile nav clearance**
Inner content wrapper must include `pb-24 md:pb-8`.

```tsx
// CORRECT
className="max-w-4xl mx-auto px-6 py-12 pb-24 md:pb-8"
// WRONG
className="max-w-4xl mx-auto px-6 py-12"
```

### backend/ai/engines/coach.py

**Fix: No session counter update in _save_message**
The `UPDATE ai_coach_sessions SET message_count...` query has been REMOVED from
`_save_message`. It caused a 2-minute statement timeout that held the SSE stream
open and caused mid-sentence cutoffs. Do not re-add it.

```python
# CORRECT — no counter update
async def _save_message(self, ...):
    result = await db.execute(text("INSERT INTO ai_coach_messages ..."), {...})
    msg_id = result.scalar()
    # Counter update removed — was causing 2-min stream stalls
    return msg_id

# WRONG — do not re-add this block
try:
    await db.execute(text("UPDATE ai_coach_sessions SET message_count..."))
except Exception as e:
    ...
```

**Fix: _safe_rollback after all caught DB exceptions**
Every `except` block that catches a DB error must call `await _safe_rollback(db)`.
This prevents PostgreSQL `InFailedSQLTransactionError` from poisoning subsequent
queries on the same connection.

```python
# CORRECT
except Exception as e:
    logger.warning("something_failed", error=str(e))
    await _safe_rollback(db)

# WRONG — missing rollback poisons the transaction
except Exception as e:
    logger.warning("something_failed", error=str(e))
```

---

## ASYNCPG RULES — NEVER VIOLATE

These cause silent bugs and are easy to get wrong.

1. **No `::type` cast syntax with named params**
   asyncpg cannot parse PostgreSQL cast syntax with `$1`-style params.
   ```python
   # WRONG
   "WHERE id = :user_id::uuid"

   # CORRECT
   "WHERE id = CAST(:user_id AS uuid)"
   ```

2. **No `::jsonb`, `::vector`, `::text[]` with named params**
   Same rule. Use `CAST()` or inline the value in an f-string for vectors.

3. **FastAPI route ordering**
   Named routes (`/history`, `/today`, `/active`) must be defined BEFORE
   catch-all routes (`/{date}`, `/{id}`) or FastAPI matches the word as a param.

4. **JSON serialisation**
   Use `json.dumps()`, never `str()` on structured data.

5. **Supabase Storage uploads**
   Use `supabase-py` client, not raw `httpx` calls.

---

## DEPLOYMENT REMINDERS

- GitHub push → Railway auto-deploys backend (~10–15 min)
- GitHub push → Vercel auto-deploys frontend (~2 min)
- Railway env var changes take effect without redeploy
- All Next.js folder names must be lowercase (Vercel on Linux is case-sensitive)
- Never hardcode env vars — all config lives in `backend/core/config.py`

---

## HOW TO USE THIS FILE

At the start of every session where code will be changed:
1. Read CLAUDE.md for project context
2. Read TODO.md for current sprint
3. Read this file for coding constraints
4. Before delivering any edited file, check the PERMANENT FIXES section
   and verify none of them have been removed

When adding a new permanent fix during a session, add it to this file
in the same commit.

---

## KNOWN BEHAVIOUR — NOT BUGS

### Interview phase showing `intro` in database
All users show `current_phase = 'intro'` in `onboarding_interview_state`. This is
the DB default from account creation. The engine falls back to `tension` (index 0)
when it sees an unknown phase, so the interview runs correctly. Cosmetic only.

Fix for new users: seed `onboarding_interview_state` with `current_phase = 'tension'`
not `intro` when the row is first created.

### Interview 400 responses for completed users
Users whose interview is `is_complete = TRUE` receive a `400 Bad Request` if they
send another message. This is correct backend behaviour. The frontend now catches
`err.status === 400` and redirects to `/dashboard` instead of showing an error.

### Push subscribe was hitting `/api/api/push/subscribe`
Fixed March 29, 2026. `NEXT_PUBLIC_API_URL` already includes `/api` — the subscribe
call must use `/push/subscribe` not `/api/push/subscribe`.

### APScheduler interview nudge jobs `RuntimeError: no running event loop`
Fixed March 29, 2026. Jobs were registered with `lambda: asyncio.create_task()`
which requires a running event loop. Replaced with `func=lambda:` passing the
coroutine directly — `AsyncIOScheduler` handles the async call itself.

### Scheduler job registration pattern
All scheduler jobs must use `func=` with an `async def` function or a lambda
returning a coroutine. Never use `asyncio.create_task()` inside a lambda passed
to `scheduler.add_job()` — APScheduler runs jobs in a thread pool where no event
loop is running.

```python
# CORRECT
scheduler.add_job(func=run_my_job, trigger=CronTrigger(...))
scheduler.add_job(func=lambda: run_my_job(param=value), trigger=CronTrigger(...))

# WRONG — RuntimeError: no running event loop
scheduler.add_job(lambda: asyncio.create_task(run_my_job()), CronTrigger(...))
```