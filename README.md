# Juggernaut Router

Benchmark-driven hybrid LLM routing agent for AMD Developer Hackathon: ACT II.

## Goal

Build a routing system that decides when to use local AMD-hosted inference and when to use remote inference, optimizing:

- accuracy
- token usage
- latency
- cost
- reproducibility

## AMD Infrastructure Proof

Initial sanity testing was run on AMD AI Notebooks with ROCm, PyTorch, and vLLM.

Evidence is stored in:

docs/amd_proof/environment_proof.txt

Confirmed:

- ROCm GPU visible through rocm-smi
- PyTorch GPU available
- vLLM imports successfully
- Qwen/Qwen2.5-0.5B-Instruct runs locally through vLLM

## Planned Strategies

- baseline_remote_all
- baseline_local_all
- hybrid_router

## Project Structure

router/       Routing logic
providers/    Local and remote inference adapters
benchmarks/   Evaluation scripts
data/         Benchmark datasets
results/      Benchmark outputs
docs/         Evidence and technical notes
tests/        Unit tests
scripts/      Utility scripts
