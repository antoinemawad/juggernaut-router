# Juggernaut Router Cloudflare Worker Demo

This is a public demo surface for the project. It is not the Track 1 Docker agent and does not include evaluator inputs, private keys, or model weights.

## Run Locally

```bash
cd demo-worker
npm install
npm run dev
```

Open `http://localhost:8787`.

## Deploy

```bash
cd demo-worker
npm run dry-run
npm run deploy
```

## Endpoints

- `GET /` interactive demo page
- `GET /health` readiness JSON
- `GET /examples` synthetic demo tasks
- `POST /route` demo category and route decision

Example:

```bash
curl -s http://localhost:8787/route \
  -H 'content-type: application/json' \
  -d '{"task_id":"demo","prompt":"Write a Python function clamp(x, low, high). Return only code."}'
```
