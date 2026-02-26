# One Goal — Complete API Reference

Base URL: `http://localhost:8000/api`
Interactive docs: `http://localhost:8000/docs` (development only)

All authenticated endpoints require:
```
Authorization: Bearer <access_token>
```

---

## Authentication `/auth`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/signup` | ❌ | Register with email + password |
| POST | `/auth/login` | ❌ | Login, returns token pair |
| POST | `/auth/oauth/callback` | ❌ | Google/Apple OAuth via Supabase |
| POST | `/auth/refresh` | ❌ | Refresh access token |
| POST | `/auth/logout` | ✅ | Revoke session |
| GET | `/auth/me` | ✅ | Get current user |
| PUT | `/auth/me` | ✅ | Update display name / timezone |
| POST | `/auth/change-password` | ✅ | Change password |
| GET | `/auth/export` | ✅ | GDPR data export |
| DELETE | `/auth/account` | ✅ | Delete account permanently |

---

## Onboarding `/onboarding`

### Flow order:
```
1. GET  /onboarding/status
2. POST /onboarding/interview/message  (repeat until is_complete=true)
3. POST /onboarding/goal-setup
4. POST /onboarding/goal-setup/clarify       (only if needs_clarification=true)
5. GET  /onboarding/goal-setup/preview
6. POST /onboarding/goal-setup/confirm
7. POST /onboarding/activate
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/onboarding/status` | Current step + next screen |
| POST | `/onboarding/interview/message` | Send interview message |
| GET | `/onboarding/interview/state` | Restore conversation history |
| POST | `/onboarding/interview/restart` | Start interview over |
| POST | `/onboarding/goal-setup` | Submit goal for decomposition |
| POST | `/onboarding/goal-setup/clarify` | Answer clarifying questions |
| GET | `/onboarding/goal-setup/preview` | Review strategy before confirming |
| POST | `/onboarding/goal-setup/confirm` | Confirm strategy |
| POST | `/onboarding/activate` | Activate + generate first tasks |

### Example: Interview message
```json
POST /onboarding/interview/message
{
  "message": "I want to build a sustainable business that lets me work from anywhere"
}

Response:
{
  "message": "That's a meaningful direction. What does 'sustainable' mean to you in this context — are you thinking financial stability, lifestyle balance, or something else?",
  "phase": "vision",
  "is_complete": false,
  "onboarding_status": "interview_started"
}
```

### Example: Goal submission
```json
POST /onboarding/goal-setup
{
  "raw_goal": "Build a SaaS product that generates $10k MRR within 12 months"
}

Response (needs clarification):
{
  "goal_id": null,
  "needs_clarification": true,
  "clarifying_questions": [
    "Do you have a specific market or customer type in mind?",
    "Are you starting from zero or building on an existing idea?"
  ],
  "strategy": null
}

Response (ready):
{
  "goal_id": "uuid",
  "needs_clarification": false,
  "clarifying_questions": [],
  "strategy": {
    "refined_statement": "...",
    "required_identity": "...",
    "objectives": [...],
    "identity_traits": [...]
  }
}
```

---

## Goals `/goals`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/goals/active` | Full active goal with objectives + traits |
| GET | `/goals/history` | All past goals |
| GET | `/goals/{id}` | Specific goal |
| PUT | `/goals/{id}` | Edit goal statement/details |
| POST | `/goals/{id}/pause` | Pause current goal |
| POST | `/goals/{id}/abandon` | Abandon with reason |
| POST | `/goals/{id}/complete` | Mark as complete |
| GET | `/goals/{id}/objectives` | List objectives |
| PUT | `/goals/{id}/objectives/{obj_id}` | Update objective status |
| GET | `/goals/traits` | Active identity traits |
| PUT | `/goals/traits/{id}` | Correct trait score |

---

## Daily Tasks `/tasks`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tasks/today` | Today's becoming task |
| GET | `/tasks/{date}` | Task for specific date (YYYY-MM-DD) |
| POST | `/tasks/{id}/start` | Enter execution mode |
| POST | `/tasks/{id}/complete` | Mark complete |
| POST | `/tasks/{id}/skip` | Skip with reason |
| GET | `/tasks/history` | Task history + stats |
| POST | `/tasks/generate` | On-demand task generation |

### Example: Complete a task
```json
POST /tasks/{id}/complete
{
  "execution_notes": "Did it early in the morning. Felt resistance at first but pushed through.",
  "actual_duration_minutes": 45
}

Response:
{
  "status": "completed",
  "message": "Task complete. Take a moment to reflect.",
  "reflection_available": true
}
```

---

## Reflections `/reflections`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reflections/questions/{task_id}` | Get AI-generated questions |
| POST | `/reflections` | Submit reflection → AI analysis |
| GET | `/reflections/today` | Today's reflection |
| GET | `/reflections/{date}` | Reflection for date |
| GET | `/reflections/history` | History + trends |
| GET | `/reflections/weekly-review` | Latest weekly evolution letter |
| GET | `/reflections/weekly-review/{date}` | Specific week's review |

### Example: Submit reflection
```json
POST /reflections
{
  "task_id": "uuid",
  "answers": [
    {
      "question": "What actually happened when you did this today?",
      "answer": "I blocked two hours in the morning and actually shipped the feature I'd been avoiding for a week. Surprised myself.",
      "question_type": "execution"
    },
    {
      "question": "What did this reveal about who you're becoming?",
      "answer": "I'm starting to trust that I can do hard things if I just start. The starting is always the hardest part.",
      "question_type": "identity"
    }
  ]
}

Response:
{
  "reflection_id": "uuid",
  "ai_feedback": "There's something important in what you noticed — the gap between anticipating difficulty and the actual experience of doing it. You're building evidence that you can trust yourself to start. That's not a small thing.",
  "sentiment": "breakthrough",
  "safety_triggered": false
}
```

---

## AI Coach `/coach`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/coach/sessions` | Create new session |
| GET | `/coach/sessions` | List recent sessions |
| GET | `/coach/sessions/active` | Get/create active session + messages |
| POST | `/coach/sessions/{id}/message` | Send message (SSE streaming) |
| DELETE | `/coach/sessions/{id}` | End session |

### Streaming coach messages
The message endpoint returns Server-Sent Events:
```javascript
const response = await fetch('/api/coach/sessions/{id}/message', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer token',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ content: 'I feel like I keep avoiding the hard tasks.' })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const chunk = decoder.decode(value);
  const lines = chunk.split('\n');

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const text = line.slice(6);
      if (text === '[DONE]') break;
      // Append text to UI
    }
  }
}
```

---

## Progress `/progress`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/progress/dashboard` | All dashboard data (single call) |
| GET | `/progress/scores` | Score breakdown with grades |
| GET | `/progress/streak` | Streak + 30-day calendar |
| GET | `/progress/timeline` | Score history for charts |
| GET | `/progress/traits/timeline` | Trait scores for radar chart |

---

## Complete User Journey Flow

```
1.  POST /auth/signup
2.  POST /onboarding/interview/message  (8-15 exchanges)
3.  POST /onboarding/goal-setup
4.  GET  /onboarding/goal-setup/preview
5.  POST /onboarding/goal-setup/confirm
6.  POST /onboarding/activate
    → User is now active

Daily loop (every day):
7.  GET  /progress/dashboard           → shows today's task
8.  POST /tasks/{id}/start             → enter execution mode
9.  POST /tasks/{id}/complete          → mark done
10. GET  /reflections/questions/{id}   → get reflection questions
11. POST /reflections                  → submit + get AI feedback
12. POST /coach/sessions/active        → optional: talk to coach

Weekly:
13. GET  /reflections/weekly-review    → Sunday evolution letter
```

---

## Error Responses

All errors follow this shape:
```json
{
  "error": "error_code",
  "detail": "Human readable message",
  "request_id": "uuid"
}
```

Common error codes:
- `validation_error` — Invalid request body (422)
- `unauthorized` — Missing or invalid token (401)
- `forbidden` — Valid token, insufficient permissions (403)
- `not_found` — Resource doesn't exist (404)
- `conflict` — Duplicate resource (409)
- `rate_limit_exceeded` — Too many requests (429)
- `ai_quota_exceeded` — Daily AI limit reached (429)
- `onboarding_incomplete` — Route requires full onboarding (403)
- `interview_required` — Must complete interview first (400)
