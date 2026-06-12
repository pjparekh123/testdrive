You are summarizing an article for a personal reading queue. Be neutral, dense, and concrete.

ARTICLE TITLE: {title}
ARTICLE TEXT:
{text}

Return JSON only, matching this schema exactly:
{
  "tldr": "One sentence, ≤25 words, factual not promotional.",
  "summary": "3–5 sentences. Cover the central claim, key evidence, and any surprising finding. No filler phrases like 'this article discusses'.",
  "tags": ["3–6 lowercase tags, single words or hyphenated, e.g. neuroscience, urban-planning, llm-evals"]
}

Rules:
- Never use the phrases "this article", "the author argues", "in this piece".
- If the article is mostly opinion, say so in the summary.
- If the article is thin (listicle, news brief), keep summary to 2 sentences.
- Return JSON only. No prose, no markdown fences.
