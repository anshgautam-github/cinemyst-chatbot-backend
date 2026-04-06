# CineMyst Chatbot Backend

This is a standalone chatbot backend for CineMyst built with:

- FastAPI
- LangChain
- LangGraph
- OpenAI
- Supabase

It is designed to answer product-aware questions about:

- mentors
- mentor specialties
- pricing
- availability
- bookings
- jobs
- the current user profile

## What it does

The service accepts a `user_id` plus a chat message. It then:

1. loads the current user from `profiles`
2. gives the model safe tool access to Supabase-backed data
3. persists chat conversations/messages
4. answers using real CineMyst data instead of hardcoded text

## Folder layout

```text
chatbot_backend/
  app/
    agent.py
    config.py
    main.py
    prompts.py
    schemas.py
    supabase_service.py
    tools.py
  .env.example
  pyproject.toml
  README.md
```

## Environment variables

Copy `.env.example` to `.env` and fill in:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- optionally `SUPABASE_SERVICE_ROLE_KEY`

`SUPABASE_SERVICE_ROLE_KEY` is recommended for a backend deployment when you want broader trusted reads. Keep it server-side only.

## Install

Using `uv`:

```bash
cd chatbot_backend
uv sync
```

Or with pip:

```bash
cd chatbot_backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
cd chatbot_backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Deploy for iOS production

To make this work from your iPhone on any network, this backend must run on a public HTTPS URL.
Your iOS app should call that URL instead of `localhost`.

### 1. Prepare environment variables

Create server-side environment variables from `.env.example`:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `APP_ENV=production`

Do not ship any of these keys inside the iOS app.

### 2. Deploy the API

This repo now includes a `Dockerfile`, so you can deploy it to platforms like:

- Render
- Railway
- Fly.io
- DigitalOcean App Platform
- an EC2/VPS with Docker

If you use Render, this repo also includes [render.yaml](/Users/user40/Documents/CINEMYSTTTTTTTT/CineMyst/chatbot_backend/render.yaml) for a simple web service setup.

Example local container test:

```bash
docker build -t cinemyst-chatbot .
docker run --env-file .env -p 8000:8000 cinemyst-chatbot
```

Once deployed, you should have a public base URL such as:

```text
https://cinemyst-chatbot.onrender.com
```

### 3. Point the iOS app to the deployed URL

In your iOS app, replace the local backend URL with your deployed base URL.

Example endpoints:

- `GET /health`
- `POST /v1/chat`
- `POST /v1/chat/stream`

### 4. Use HTTPS in production

iOS requires HTTPS for normal production networking unless you add App Transport Security exceptions.
Use a deployment provider that gives you SSL by default.

### 5. Important security fix before launch

Right now the API accepts a raw `user_id` from the client and trusts it.
That means a malicious user could try another user's ID and read their profile-aware answers.

Before launch, the backend should verify the logged-in Supabase user from an auth token and derive the user ID on the server instead of trusting the request body.

### 6. Important scaling note

LangGraph conversation memory is currently stored in-process with `MemorySaver()`.
This means conversation state is lost on restart and is not shared across multiple server instances.

For production, move chat memory to a persistent store if you need multi-device or long-lived conversations.

## API

### Health

```bash
curl http://localhost:8000/health
```

### Chat

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "cddf9a93-0c6f-4e18-9ccb-0a0e3d6cf88a",
    "conversation_id": "demo-thread-1",
    "message": "Suggest 3 mentors for dubbing under 2000 and tell me their prices."
  }'
```

### Preview user context

```bash
curl http://localhost:8000/v1/users/cddf9a93-0c6f-4e18-9ccb-0a0e3d6cf88a/context
```

### List conversations

```bash
curl http://localhost:8000/v1/users/cddf9a93-0c6f-4e18-9ccb-0a0e3d6cf88a/conversations
```

### Load conversation messages

```bash
curl http://localhost:8000/v1/users/cddf9a93-0c6f-4e18-9ccb-0a0e3d6cf88a/conversations/demo-thread-1/messages
```

## Tooling approach

The model does not receive arbitrary SQL access.

Instead it gets a curated tool layer:

- `get_user_profile`
- `get_user_bookings`
- `search_mentors`
- `get_mentor_details`
- `get_mentor_availability`
- `search_jobs`
- `recommend_mentors_for_user`

This is much safer and more stable than free-form SQL generation.

## Notes for iOS integration

Your iOS app can call this backend from a future `ChatbotService` with:

- the current logged-in `profiles.id`
- the user message
- an optional `conversation_id`

Recommended request body:

```json
{
  "user_id": "current-profile-id",
  "conversation_id": "optional-thread-id",
  "message": "Which mentors are best for acting under ₹2500?"
}
```

## Current CineMyst tables used

The implementation is wired for:

- `profiles`
- `mentor_profiles`
- `mentorship_sessions`
- `mentor_availability_slots`
- `jobs`
- `chat_conversations`
- `chat_messages`

## Required Supabase tables for persistent chat

Create these tables in Supabase so conversations appear again when the user reopens chat:

```sql
create table if not exists public.chat_conversations (
  conversation_id text primary key,
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text not null default 'New chat',
  last_message_preview text not null default '',
  created_at timestamptz not null default now(),
  last_message_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id text not null references public.chat_conversations(conversation_id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_chat_conversations_user_last_message_at
  on public.chat_conversations(user_id, last_message_at desc);

create index if not exists idx_chat_messages_conversation_created_at
  on public.chat_messages(conversation_id, created_at asc);

create or replace function public.touch_chat_conversation_last_message_at()
returns trigger
language plpgsql
as $$
begin
  update public.chat_conversations
  set last_message_at = new.created_at
  where conversation_id = new.conversation_id;
  return new;
end;
$$;

drop trigger if exists trg_touch_chat_conversation_last_message_at on public.chat_messages;

create trigger trg_touch_chat_conversation_last_message_at
after insert on public.chat_messages
for each row execute function public.touch_chat_conversation_last_message_at();
```

## Recommended next step

After this backend is running, the next clean addition is a simple iOS chat screen plus a small API client inside the app.
