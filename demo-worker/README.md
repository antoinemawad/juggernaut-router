# Juggernaut Router Track 1 Demo Worker

This Cloudflare Worker is a public, informative demo for the AMD Developer Hackathon Track 1 project.

It does not run the private evaluator and does not contain secrets or model weights. The official agent remains the Docker image.

## What It Demonstrates

- Synthetic examples for the Track 1 categories
- Prompt classification
- Route intent
- Evaluator-style `{ task_id, answer }` output shape
- A small web UI for judges or viewers

## Run Locally

```bash
cd demo-worker
npm install
npm run check
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

- `GET /` web demo
- `GET /health` health check
- `GET /tasks` synthetic Track 1 tasks
- `GET /results` evaluator-style synthetic results
- `POST /route` classify and route a single prompt

Example:

```bash
curl -s http://localhost:8787/route \
  -H 'content-type: application/json' \
  -d '{"task_id":"demo","prompt":"Write a Python function clamp(x, low, high). Return only code."}'
```
