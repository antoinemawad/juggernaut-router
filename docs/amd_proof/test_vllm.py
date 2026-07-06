from vllm import LLM, SamplingParams
import time


def main():
    model_name = "Qwen/Qwen2.5-0.5B-Instruct"

    prompts = [
        "Classify this task as easy, medium, or hard: What is 2+2?",
        "Answer briefly: What is the purpose of a routing agent?"
    ]

    sampling_params = SamplingParams(
        temperature=0.0,
        max_tokens=80
    )

    start = time.time()

    llm = LLM(
        model=model_name,
        gpu_memory_utilization=0.60
    )

    outputs = llm.generate(prompts, sampling_params)

    elapsed = time.time() - start

    for output in outputs:
        print("=" * 80)
        print("PROMPT:", output.prompt)
        print("OUTPUT:", output.outputs[0].text.strip())

    print("=" * 80)
    print(f"Elapsed seconds: {elapsed:.2f}")


if __name__ == "__main__":
    main()
