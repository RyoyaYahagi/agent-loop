# Local Dev Server Testing in Docker Sandbox

## Problem

The user wants to verify UI changes by running the Next.js app locally, but the Docker sandbox environment has constraints:
- `npm run dev` (Turbopack) has process/port management issues in background
- `browser_navigate` to `localhost:3000` fails with `ERR_CONNECTION_REFUSED`
- Supabase auth/DB is not running, so authenticated pages time out

## Recommended Approach: Production Build + Start

Instead of `npm run dev`, use `npm run build` then `npm start`:

```bash
cd /workspace/dev/app/Ruletrade-AI

# 1. Ensure MOCK_AUTH_EMAIL is set in .env.local
cat >> .env.local << 'EOF'
MOCK_AUTH_EMAIL=dev@ruletrade.local
EOF

# 2. Build
npm run build

# 3. Start production server with explicit HOSTNAME
HOSTNAME=0.0.0.0 PORT=3000 npm start
```

## Accessing the Server

In the Docker sandbox, `browser_navigate` to `localhost:3000` fails. Use the container's IP:

```bash
# Find container IP
hostname -i
# → 172.17.0.4

# Test with curl
curl -s http://172.17.0.4:3000/ | grep -o '<title>[^<]+</title>'
```

Or use `browser_navigate` with the container IP:
```
browser_navigate url="http://172.17.0.4:3000/rules/new"
```

## Killing Stuck Processes

If a previous server is holding port 3000, find and kill it via `/proc`:

```bash
# Find the PID owning port 3000 (inode lookup)
PORT_HEX=$(printf '%04X' 3000)  # → 0BB8
grep ":${PORT_HEX}" /proc/net/tcp6 /proc/net/tcp

# Find which PID owns the socket inode
for pid in /proc/[0-9]*; do
  for fd in $pid/fd/*; do
    link=$(readlink $fd 2>/dev/null)
    if echo "$link" | grep -q "11935387"; then  # replace with your inode
      echo "PID $(basename $pid) owns the port"
      kill -9 $(basename $pid)
    fi
  done
done
```

## Smoke Test Commands

```bash
# Verify page renders
curl -s http://172.17.0.4:3000/dashboard | grep "新しいルールを作る"

# Verify form labels
curl -s http://172.17.0.4:3000/rules/new | grep -oE '<label[^>]*>[^<]+</label>'

# Verify no server errors (no __next_error__ in response)
curl -s http://172.17.0.4:3000/rules/new | grep -c "__next_error__" || echo "OK"
```

## Pages That Require Supabase DB

Pages that call `supabase.auth.getUser()` or query the DB directly will time out or redirect to `/login` unless:
1. `getCurrentUser()` is mocked (see MOCK_AUTH pattern in main skill)
2. DB calls are wrapped in try/catch with fallbacks

If the page still redirects to `/login`, check that `getCurrentUser()` mock is active and that `NODE_ENV` does not gate the mock.

## Environment Variables for Sandbox Testing

```env
# .env.local
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<dummy>
SUPABASE_SERVICE_ROLE_KEY=<dummy>
AI_PROVIDER=mock
MOCK_AUTH_EMAIL=dev@ruletrade.local
```
