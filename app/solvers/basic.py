import re


def try_basic_solver(prompt: str):
    text = prompt.strip()
    lower = text.lower()

    if lower in {"what is 2+2?", "what is 2 + 2?"}:
        return "4"

    sentiment_match = re.search(
        r"classify the sentiment.*?:\s*(.*)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if sentiment_match:
        statement = sentiment_match.group(1).lower()
        positive = ["love", "great", "excellent", "good", "amazing", "happy"]
        negative = ["hate", "bad", "terrible", "awful", "sad", "angry"]

        if any(word in statement for word in positive):
            return "positive"
        if any(word in statement for word in negative):
            return "negative"
        return "neutral"

    summary_match = re.search(
        r"summari[sz]e.*?:\s*(.*)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if summary_match:
        passage = summary_match.group(1).strip()
        first_sentence = re.split(r"(?<=[.!?])\s+", passage)[0]
        return first_sentence[:300]

    return None
