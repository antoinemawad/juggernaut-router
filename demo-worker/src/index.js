const EXAMPLES = [
  {
    task_id: "demo_sentiment",
    prompt: "Classify the sentiment as positive, negative, or neutral: The setup was easy, but the results were unreliable.",
  },
  {
    task_id: "demo_math",
    prompt: "A router saves 25% on a 240 token task. How many tokens are saved? Return only the number.",
  },
  {
    task_id: "demo_code",
    prompt: "Write a Python function clamp(x, low, high). Return only code.",
  },
  {
    task_id: "demo_summary",
    prompt: "Summarise: Juggernaut Router classifies tasks locally and escalates risky prompts to Fireworks for accuracy.",
  },
];

const CATEGORY_RULES = [
  ["code_generation", /\b(write|implement|function|return only code|python|javascript)\b/i],
  ["mathematical_reasoning", /\b(percent|tokens?|saved|calculate|sum|cost|price|\d+)\b/i],
  ["sentiment_classification", /\b(sentiment|positive|negative|neutral)\b/i],
  ["text_summarisation", /\b(summarise|summarize|summary|condense)\b/i],
  ["named_entity_recognition", /\b(entity|entities|person|org|location|date)\b/i],
  ["code_debugging", /\b(debug|bug|fix this code|traceback|error)\b/i],
  ["logical_deductive_reasoning", /\b(logic|deduce|constraint|who|which)\b/i],
];

function classify(prompt) {
  for (const [category, pattern] of CATEGORY_RULES) {
    if (pattern.test(prompt)) return category;
  }
  return "factual_knowledge";
}

function routeTask(task) {
  const prompt = String(task.prompt || "");
  const category = classify(prompt);
  if (category === "sentiment_classification") {
    return {
      route: "demo_local",
      category,
      answer: /unreliable|bad|failed|broken/i.test(prompt) ? "negative" : "neutral",
    };
  }
  if (category === "mathematical_reasoning" && /25%.*240|240.*25%/i.test(prompt)) {
    return { route: "demo_deterministic", category, answer: "60" };
  }
  if (category === "code_generation" && /clamp/i.test(prompt)) {
    return {
      route: "demo_template",
      category,
      answer: "def clamp(x, low, high):\n    return max(low, min(high, x))",
    };
  }
  if (category === "text_summarisation") {
    return {
      route: "demo_local",
      category,
      answer: "Juggernaut Router classifies tasks locally and escalates risky prompts to Fireworks.",
    };
  }
  return {
    route: "demo_remote_placeholder",
    category,
    answer: "This demo would route the task to the configured Fireworks model in the Docker agent.",
  };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function htmlPage() {
  const examples = EXAMPLES.map(
    (task) => `<button data-prompt="${escapeHtml(task.prompt)}">${escapeHtml(task.task_id)}</button>`
  ).join("");
  return new Response(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Juggernaut Router Demo</title>
  <style>
    :root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; background: #f8fafc; }
    body { margin: 0; }
    main { max-width: 1040px; margin: 0 auto; padding: 40px 20px; }
    h1 { font-size: clamp(34px, 6vw, 68px); line-height: 1; margin: 0 0 16px; }
    p { color: #475569; font-size: 18px; line-height: 1.55; max-width: 760px; }
    textarea, pre { box-sizing: border-box; width: 100%; border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px; background: white; color: #0f172a; font: 14px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
    textarea { min-height: 140px; resize: vertical; }
    .grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; margin-top: 28px; }
    .examples { display: flex; flex-wrap: wrap; gap: 10px; margin: 20px 0; }
    button { border: 0; border-radius: 8px; padding: 10px 14px; background: #0f172a; color: white; cursor: pointer; font-weight: 700; }
    .secondary { background: #2563eb; }
    @media (max-width: 780px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <h1>Juggernaut Router Demo</h1>
    <p>Try synthetic Track 1 prompts and see the same kind of category and route decisions used by the Docker agent. This Worker is a public demo surface only; it does not include evaluator inputs or secrets.</p>
    <div class="examples">${examples}</div>
    <div class="grid">
      <section>
        <textarea id="prompt">Write a Python function clamp(x, low, high). Return only code.</textarea>
        <p><button class="secondary" id="run">Route Prompt</button></p>
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
        body: JSON.stringify({ task_id: 'web_demo', prompt: prompt.value })
      });
      output.textContent = JSON.stringify(await response.json(), null, 2);
    });
  </script>
</body>
</html>`, {
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") return htmlPage(env);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, service: env.DEMO_NAME || "Juggernaut Router Demo" });
    }
    if (request.method === "GET" && url.pathname === "/examples") return json(EXAMPLES);
    if (request.method === "POST" && url.pathname === "/route") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "Expected JSON body with task_id and prompt." }, 400);
      }
      if (!body || typeof body.prompt !== "string") {
        return json({ error: "Missing prompt." }, 400);
      }
      const routed = routeTask(body);
      return json({ task_id: body.task_id || "demo_task", ...routed });
    }
    return json({ error: "Not found" }, 404);
  },
};
