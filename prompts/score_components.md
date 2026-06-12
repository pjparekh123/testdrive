You are scoring an article for a personal reading queue. Return JSON only.

USER INTERESTS:
{interests_yaml}

ARTICLE:
- Title: {title}
- Tldr: {tldr}
- Summary: {summary}
- Tags: {tags}
- Word count: {word_count}
- Read minutes: {read_minutes}
- Published: {published_at}
- Days since published: {days_old}

USER'S RECENT READING (last 20 kept items, for novelty comparison):
{recent_kept_titles}

Score each component 0–10. Be honest; most articles are mediocre.

Return JSON only:
{
  "topic_match": {"score": 0-10, "reason": "≤20 words"},
  "recency_value": {"score": 0-10, "reason": "is this time-sensitive or evergreen?"},
  "effort_payoff": {"score": 0-10, "reason": "is the length justified?"},
  "surprise": {"score": 0-10, "reason": "does this challenge the user's usual reading?"}
}

Note: novelty and source_reputation are computed separately. Don't score them.
