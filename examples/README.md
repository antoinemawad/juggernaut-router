# Examples

This directory contains safe synthetic examples for local demos. They are not private evaluator inputs.

Run with Python:

```bash
INPUT_PATH=examples/sample_tasks.json \
OUTPUT_PATH=/tmp/juggernaut-results.json \
python3 -m app.main

python3 scripts/validate_submission_io.py /tmp/juggernaut-results.json
```

Run with Docker:

```bash
./scripts/demo.sh
```

`expected_sample_output.json` shows the required schema, not a guaranteed answer for every runtime configuration.
