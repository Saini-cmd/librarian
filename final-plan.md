# Librarian AI — Final Implementation Plan

## User Flow

```
/ → Landing Page (marketing)
  ├── Hero, Features, How It Works, Footer
  ├── Sign In / Sign Up (Clerk modal)
  │
  └── → /app (authenticated)
        ├── Sidebar: past conversations (click to load history + repo state)
        │   ├── "New Chat" button
        │   ├── Conversation list (grouped by repo, ordered by date)
        │   └── Settings link
        │
        └── Main area:
              ├── No active conversation → Repo URL input + Process button
              │   (shows progress bar during pipeline)
              │
              └── After ingestion / past conversation selected → Chat UI
                  - Message history loaded from DB
                  - Streaming chat (SSE)
                  - Messages auto-saved to DB
```

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend Framework | React 18 + Vite 8 |
| UI Library | daisyUI 5 (Tailwind CSS 4) |
| Design Theme | Industrial Brutalist (Tactical Telemetry Dark mode) |
| Auth | Clerk (existing) |
| Database | Supabase PostgreSQL via SQLAlchemy async + asyncpg |
| Backend | FastAPI (existing) |

## Database Schema (Supabase PostgreSQL)

### `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | `gen_random_uuid()` |
| clerk_id | TEXT UNIQUE | From Clerk JWT `sub` |
| email | TEXT | |
| name | TEXT | |
| avatar_url | TEXT | |
| created_at | TIMESTAMPTZ | `default now()` |
| updated_at | TIMESTAMPTZ | `default now()` |

### `conversations`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | CASCADE delete |
| repo_name | TEXT | |
| repo_url | TEXT | |
| title | TEXT | Auto-generated or user-set |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `messages`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| conversation_id | UUID FK → conversations | CASCADE delete |
| role | TEXT | `'user'` or `'assistant'` |
| content | TEXT | |
| citations | JSONB | Citation metadata |
| created_at | TIMESTAMPTZ | |

### `user_repos`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | CASCADE delete |
| repo_name | TEXT | |
| repo_url | TEXT | |
| status | TEXT | `'indexed'`, `'indexing'`, `'failed'` |
| created_at | TIMESTAMPTZ | |

## Backend Structure

```
backend/
├── __init__.py
├── AGENTS.md
├── database.py           # Async SQLAlchemy engine, session factory, get_db
├── models.py             # User, Conversation, Message, UserRepo ORM
├── auth.py               # Clerk JWT verify + webhook verify + get_current_user
├── main.py               # FastAPI app, CORS, router mounts, lifespan
├── routers/
│   ├── __init__.py
│   ├── auth_webhook.py   # POST /api/webhooks/clerk (user.created/updated/deleted)
│   ├── users.py          # GET/PATCH /api/users/me
│   ├── conversations.py  # CRUD /api/conversations
│   └── repositories.py   # CRUD /api/repositories
└── migrations/           # Alembic
    ├── env.py
    ├── script.py.mako
    └── versions/
        └── 001_initial.py
```

### API Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | No | Health check |
| GET | `/api/status` | No | Pipeline status |
| POST | `/api/reset` | JWT | Wipe data (protected) |
| POST | `/api/process` | JWT | Ingest repo → creates Conversation + UserRepo |
| POST | `/api/chat` | JWT | Query → retrieve → generate (saves to DB) |
| POST | `/api/chat/stream` | JWT | SSE streaming (accepts `conversation_id`, saves msgs) |
| POST | `/api/webhooks/clerk` | Webhook secret | Sync user create/update/delete |
| GET | `/api/users/me` | JWT | Current user profile |
| PATCH | `/api/users/me` | JWT | Update profile |
| GET | `/api/conversations` | JWT | List user conversations |
| POST | `/api/conversations` | JWT | Create conversation |
| GET | `/api/conversations/{id}` | JWT | Get conversation + messages |
| DELETE | `/api/conversations/{id}` | JWT | Delete conversation |
| GET | `/api/repositories` | JWT | List user's indexed repos |
| POST | `/api/repositories` | JWT | Track repo |
| DELETE | `/api/repositories/{id}` | JWT | Remove repo |

## Frontend Structure

```
frontend/src/
├── api/
│   └── client.js             # Axios instance + auth interceptor
├── components/
│   ├── Layout.jsx            # App shell (sidebar + main area)
│   ├── Sidebar.jsx           # Conversation list, new chat, settings link
│   ├── LandingHero.jsx       # Landing page hero
│   ├── LandingFeatures.jsx   # Landing page features grid
│   ├── LandingHowItWorks.jsx # Landing page steps
│   ├── LandingFooter.jsx     # Landing page footer
│   ├── MessageContent.jsx    # Markdown renderer with citations
│   ├── RepoInput.jsx         # GitHub URL input + process button
│   ├── ProgressBar.jsx       # Pipeline progress indicator
│   └── ChatMessages.jsx      # Message list with auto-scroll
├── hooks/
│   ├── useMarkdown.js        # Markdown → sanitized HTML
│   └── useApi.js             # API call helper (loading/error/data)
├── pages/
│   ├── LandingPage.jsx       # Full marketing page
│   ├── AppPage.jsx           # Main app (sidebar + repo/chat)
│   └── SettingsPage.jsx      # User profile settings
├── App.jsx                   # Router: / → Landing, /app → AppPage, /settings → Settings
├── main.jsx                  # Entry point (ClerkProvider + BrowserRouter)
└── styles.css                # Tailwind + daisyUI + brutalist theme
```

### Routes

| Path | Page | Auth |
|---|---|---|
| `/` | LandingPage | Public |
| `/app` | AppPage | Protected |
| `/settings` | SettingsPage | Protected |

## Design System: Industrial Brutalist (Tactical Telemetry Dark)

Based on [industrial-brutalist-ui](https://skills.sh/leonxlnx/taste-skill/industrial-brutalist-ui) skill.

- **Substrate:** Dark mode only — `#0A0A0A` background, `#EAEAEA` foreground
- **Accent:** Aviation Red `#E61919` — single accent color
- **Corners:** Zero border-radius on everything (90° only)
- **Typography:** Heavy sans-serif headers (Inter Black), monospace for data (JetBrains Mono)
- **Grid:** Strict CSS Grid with visible `1px` borders
- **Borders:** Thick (`2px` solid) compartmentalization lines
- **Effects:** CRT scanlines, mechanical noise grain, no shadows/gradients
- **daisyUI theme:** Custom theme with `--radius-*: 0rem`, `--border: 2px`, brutalist color palette

## Implementation Order

### Phase 1: Frontend Foundation
1. Install Tailwind CSS v4 + daisyUI 5 npm packages
2. Create brutalist daisyUI theme in CSS entry point
3. Set up Vite config with Tailwind CSS v4 plugin
4. Create new directory structure (pages/, components/, api/, hooks/)
5. Rewrite `main.jsx` with BrowserRouter
6. Rewrite `App.jsx` as router (/, /app, /settings)
7. Create `api/client.js` — Axios with auth interceptor
8. Create hooks: `useMarkdown.js`, `useApi.js`
9. Create Layout, Sidebar, and page skeletons

### Phase 2: Landing Page
1. LandingHero component (hero section with CTA)
2. LandingFeatures component (feature grid)
3. LandingHowItWorks component (step-by-step)
4. LandingFooter component
5. Assemble LandingPage

### Phase 3: Main App UI
1. RepoInput component (GitHub URL + process button)
2. ProgressBar component (pipeline stages)
3. ChatMessages component (message list with auto-scroll)
4. MessageContent component (markdown rendering)
5. Sidebar component (conversation list + new chat)
6. Layout component (sidebar + main area orchestration)
7. Assemble AppPage
8. SettingsPage (user profile)

### Phase 4: Backend Database
1. Add dependencies to requirements.txt
2. Create `backend/database.py`
3. Create `backend/models.py`
4. Set up Alembic + initial migration
5. Add `.env` entries

### Phase 5: Backend Routers
1. Create `backend/routers/__init__.py`
2. `auth_webhook.py` — Clerk webhook handler
3. `users.py` — user profile endpoints
4. `conversations.py` — conversation CRUD
5. `repositories.py` — user repo CRUD

### Phase 6: Backend Integration
1. Update `backend/auth.py` — webhook verification, get_current_user returns User
2. Update `backend/main.py` — mount routers, lifespan handler
3. Update `/api/process` — create Conversation + UserRepo
4. Update `/api/chat/stream` — accept conversation_id, save messages

### Phase 7: Polish
1. Loading skeletons for all views
2. Empty states (no conversations, no repos)
3. Error states with retry
4. Toast notifications
5. Typing indicator
6. Keyboard shortcuts
7. Responsive design tweaks
