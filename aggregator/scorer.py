from .config import MAX_TOTAL_ARTICLES


def score_and_sort(articles):
    seen = set()
    unique = []
    for a in articles:
        key = a["link"].rstrip("/")
        if key not in seen and a["title"]:
            seen.add(key)
            unique.append(a)

    for a in unique:
        a["score"] = a["tier_weight"] * 100 - a["position"] * 5

    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique[:MAX_TOTAL_ARTICLES]
