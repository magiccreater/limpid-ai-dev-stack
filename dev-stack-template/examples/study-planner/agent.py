"""
Study Planner Agent — for your son (and productizable later).

Generates weekly plans with spaced-repetition style review slots.
"""

from __future__ import annotations

import asyncio
import json
import sys

from devstack_shared.llm import get_llm
from devstack_shared.jev_client import try_decide


async def build_plan(
    subject: str,
    hours_per_week: float = 5,
    level: str = "high-school",
    weeks: int = 4,
) -> dict:
    # Optional: let Jev rate subject difficulty (None when Jev is off or unavailable)
    difficulty = await try_decide(
        state=f"Subject: {subject}, level: {level}",
        questions={
            "difficulty": {
                "type": "score",
                "instructions": "How demanding is this subject for the given level?",
                "criteria": {
                    "0": "Easy / review",
                    "1": "Moderate",
                    "2": "Challenging",
                    "3": "Very hard / advanced",
                },
            }
        },
    )

    llm = get_llm(tier="hybrid")
    prompt = f"""You are an expert study coach for students.
Subject: {subject}
Level: {level}
Available hours per week: {hours_per_week}
Plan length: {weeks} weeks
Difficulty signal: {difficulty or 'not available'}

Create a practical study plan as JSON with:
{{
  "overview": "1-2 sentence goal",
  "weekly": [
    {{
      "week": 1,
      "focus": "...",
      "sessions": [
        {{"day": "Mon", "minutes": 45, "activity": "Learn concept X", "type": "new"}},
        {{"day": "Wed", "minutes": 30, "activity": "Practice problems", "type": "practice"}},
        {{"day": "Fri", "minutes": 20, "activity": "Review flashcards", "type": "review"}}
      ]
    }}
  ],
  "tips": ["...", "..."]
}}

Respect the hour budget. Prefer short focused sessions. Include review days.
Return ONLY valid JSON.
"""
    res = await llm.ainvoke(prompt)
    try:
        return json.loads(res.content)
    except json.JSONDecodeError:
        return {"raw": res.content, "difficulty": difficulty}


if __name__ == "__main__":
    subject = sys.argv[1] if len(sys.argv) > 1 else "Calculus"
    plan = asyncio.run(build_plan(subject))
    print(json.dumps(plan, indent=2, ensure_ascii=False))
