from app.solvers.basic import try_basic_solver
from app.fireworks_client import ask_fireworks


def answer_prompt(prompt: str) -> str:
    local_answer = try_basic_solver(prompt)

    if local_answer is not None:
        return local_answer

    return ask_fireworks(prompt)
