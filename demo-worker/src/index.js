const TRACK1_TASKS = [
  {
    task_id: "factual_fireworks_base_url",
    category: "factual_knowledge",
    prompt: "Explain why a Track 1 agent should use FIREWORKS_BASE_URL instead of hardcoding a public endpoint.",
  },
  {
    task_id: "math_token_savings",
    category: "mathematical_reasoning",
    prompt: "A router saves 25% of a 240 token call. How many tokens are saved? Return only the number.",
  },
  {
    task_id: "sentiment_tradeoff",
    category: "sentiment_classification",
    prompt: "Classify sentiment: The setup was fast, but the answers were unreliable.",
  },
  {
    task_id: "summary_router",
    category: "text_summarisation",
    prompt: "Summarise: Juggernaut Router classifies tasks, solves safe ones locally, and escalates risky prompts to Fireworks.",
  },
  {
    task_id: "ner_sentence",
    category: "named_entity_recognition",
    prompt: "Extract entities: Lisa Su announced AMD updates in San Jose on July 10, 2026.",
  },
  {
    task_id: "code_clamp",
    category: "code_generation",
    prompt: "Write a Python function clamp(x, low, high). Return only code.",
  },
];

const ROUTE_HINTS = {
  factual_knowledge: "fireworks_when_configured",
  mathematical_reasoning: "deterministic_or_model",
  sentiment_classification: "deterministic_or_local",
  text_summarisation: "local_or_fireworks",
  named_entity_recognition: "local_or_fireworks",
  code_debugging: "fireworks_or_template",
  logical_deductive_reasoning: "fireworks_or_deterministic",
  code_generation: "template_or_fireworks",
};

function classify(prompt) {
  const text = String(prompt || "");
  if (/\bdebug|traceback|bug|fix this code\b/i.test(text)) return "code_debugging";
  if (/\bwrite|implement|function|return only code|python\b/i.test(text)) return "code_generation";
  if (/\bextract entities|named entities|person|organization|location|date\b/i.test(text)) return "named_entity_recognition";
  if (/\bsummarise|summarize|summary|condense\b/i.test(text)) return "text_summarisation";
  if (/\bsentiment|positive|negative|neutral\b/i.test(text)) return "sentiment_classification";
  if (/\bpercent|tokens?|calculate|\d+\b/i.test(text)) return "mathematical_reasoning";
  if (/\blogic|deduce|constraint|cannot determine\b/i.test(text)) return "logical_deductive_reasoning";
  return "factual_knowledge";
}

function answer(task) {
  const prompt = String(task.prompt || "");
  const category = classify(prompt);
  let route = ROUTE_HINTS[category] || "classify_then_route";
  let result = "In the Docker agent, this category is routed through validation and may escalate to Fireworks.";

  if (category === "mathematical_reasoning" && /25%.*240|240.*25%/i.test(prompt)) {
    route = "demo_deterministic";
    result = "60";
  } else if (category === "sentiment_classification") {
    route = "demo_local_rule";
    result = /unreliable|failed|bad|broken/i.test(prompt) ? "negative" : "neutral";
  } else if (category === "text_summarisation") {
    route = "demo_summary";
    result = "Juggernaut Router solves safe tasks locally and escalates risky prompts to Fireworks.";
  } else if (category === "named_entity_recognition") {
    route = "demo_extraction";
    result = "Lisa Su: PERSON; AMD: ORG; San Jose: LOCATION; July 10, 2026: DATE";
  } else if (category === "code_generation" && /clamp/i.test(prompt)) {
    route = "demo_template";
    result = "def clamp(x, low, high):\n    return max(low, min(high, x))";
  } else if (category === "factual_knowledge") {
    route = "demo_fireworks_hint";
    result = "Using FIREWORKS_BASE_URL lets the evaluator inject the correct private Fireworks endpoint and token path at runtime.";
  }

  return {
    task_id: task.task_id || "demo_task",
    category,
    route,
    answer: result,
  };
}

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function page(env) {
  const buttons = TRACK1_TASKS.map((task) => {
    return `<button data-prompt="${escapeHtml(task.prompt)}">${escapeHtml(task.category)}</button>`;
  }).join("");
  return new Response(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(env.DEMO_TITLE || "Juggernaut Router Demo")}</title>
  <style>
    :root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #0f172a; background: #f8fafc; }
    body { margin: 0; }
    main { max-width: 1100px; margin: 0 auto; padding: 42px 20px; }
    h1 { margin: 0; font-size: clamp(34px, 7vw, 72px); line-height: .95; max-width: 900px; }
    p { font-size: 18px; line-height: 1.55; color: #475569; max-width: 850px; }
    .examples { display: flex; flex-wrap: wrap; gap: 10px; margin: 24px 0; }
    button { border: 0; border-radius: 7px; background: #111827; color: white; padding: 10px 13px; font-weight: 800; cursor: pointer; }
    .run { background: #047857; }
    .grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; margin-top: 26px; }
    textarea, pre { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 8px; background: white; color: #0f172a; padding: 14px; font: 14px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
    textarea { min-height: 170px; resize: vertical; }
    pre { min-height: 170px; white-space: pre-wrap; }
    .note { border-left: 4px solid #0891b2; padding-left: 14px; }
    @media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <h1>Juggernaut Router Track 1 Demo</h1>
    <p class="note">This Worker is an informative public demo using synthetic prompts. The official submission is the Docker image that reads <code>/input/tasks.json</code> and writes <code>/output/results.json</code>.</p>
    <p>Pick a Track 1 category or paste a prompt to see classification, route intent, and evaluator-style output.</p>
    <div class="examples">${buttons}</div>
    <div class="grid">
      <section>
        <textarea id="prompt">${escapeHtml(TRACK1_TASKS[0].prompt)}</textarea>
        <p><button class="run" id="run">Route Prompt</button></p>
      </section>
      <section>
        <pre id="output">{}</pre>
      </section>
    </div>
  </main>
  <script>
    const prompt = document.querySelector('#prompt');
    const output = document.querySelector('#output');
    document.querySelectorAll('[data-prompt]').forEach((button) => {
      button.addEventListener('click', () => { prompt.value = button.dataset.prompt; });
    });
    document.querySelector('#run').addEventListener('click', async () => {
      const response = await fetch('/route', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ task_id: 'worker_demo', prompt: prompt.value })
      });
      output.textContent = JSON.stringify(await response.json(), null, 2);
    });
  </script>
</body>
</html>`, {
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") return page(env);
    if (request.method === "GET" && url.pathname === "/health") return json({ ok: true, event: "AMD Developer Hackathon Track 1" });
    if (request.method === "GET" && url.pathname === "/tasks") return json(TRACK1_TASKS);
    if (request.method === "GET" && url.pathname === "/results") return json(TRACK1_TASKS.map(answer));
    if (request.method === "POST" && url.pathname === "/route") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "Expected JSON request body." }, 400);
      }
      if (!body || typeof body.prompt !== "string") return json({ error: "Missing prompt." }, 400);
      return json(answer(body));
    }
    return json({ error: "Not found" }, 404);
  },
};
