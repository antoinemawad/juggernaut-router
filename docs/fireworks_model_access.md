# Fireworks Model Access

Purpose: separate model quality from Fireworks access/deployment readiness during Track 1 development.

## Official Aliases

The final router must keep all five official aliases configurable through `ALLOWED_MODELS`:

- `minimax-m3`
- `kimi-k2p7-code`
- `gemma-4-31b-it`
- `gemma-4-26b-a4b-it`
- `gemma-4-31b-it-nvfp4`

Do not hard-remove Gemma aliases and do not replace official aliases permanently with private deployment IDs.

## Verified Development Behavior

Kimi and Minimax can be serverless-callable in dev when the current Fireworks project/key exposes them.

Gemma 4 models may require an on-demand deployment in the current dev account/project. While a Gemma deployment is `CREATING`, `INITIALIZING`, or `STARTING`, `chat/completions` can return `404 NOT_FOUND`. This is a deployment readiness/access issue, not a model-quality failure.

After the `gemma-4-26b-a4b-it` on-demand deployment became ready, this official model path returned `200 OK`:

```text
accounts/fireworks/models/gemma-4-26b-a4b-it
```

The Fireworks dashboard may show a private deployment path such as:

```text
accounts/antoinemawad-j26hhi0/deployments/<deployment-id>
```

Private deployment paths are debug candidates only. Runtime recommendations and final router config should prefer official allowed aliases/model paths.

## Diagnostic Commands

Test Kimi:

```bash
python3 scripts/debug_fireworks_models.py \
  --models kimi-k2p7-code \
  --out-json eval_runs/access_kimi_k2p7.json \
  --out-md eval_runs/access_kimi_k2p7.md
```

Test Minimax:

```bash
python3 scripts/debug_fireworks_models.py \
  --models minimax-m3 \
  --out-json eval_runs/access_minimax_m3.json \
  --out-md eval_runs/access_minimax_m3.md
```

Test Gemma after manually creating an on-demand deployment:

```bash
python3 scripts/debug_fireworks_models.py \
  --models gemma-4-26b-a4b-it \
  --account-id antoinemawad-j26hhi0 \
  --check-deployments \
  --wait-for-deployment-ready \
  --wait-timeout-seconds 1800 \
  --poll-interval-seconds 30 \
  --out-json eval_runs/access_gemma_4_26b_a4b_it.json \
  --out-md eval_runs/access_gemma_4_26b_a4b_it.md
```

For live tests, deploy one Gemma model at a time, wait until ready, run focused tests, then stop/delete the deployment to avoid burning credits.

## Scoring Rule

Official judging must call Fireworks through the injected `FIREWORKS_BASE_URL`. Normal Fireworks API testing is development evidence only. Access/deployment failures should be excluded from model-quality scoring and reported as access evidence.
