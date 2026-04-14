from __future__ import annotations

import json
import re
from typing import Any, Optional

from src.analyzer import get_analyzer
from src.schemas.screening_ai_review import (
    ScreeningAiReviewResult,
    build_rules_fallback_review,
    normalize_screening_ai_review_payload,
)
from src.schemas.trading_types import CandidateDecision
from src.services.screening_ai_review_guard import ScreeningAiReviewGuard
from src.services.screening_ai_review_prompt_builder import (
    SCREENING_AI_REVIEW_PROMPT_VERSION,
    ScreeningAiReviewPromptBuilder,
)


class ScreeningAiReviewService:
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        prompt_builder: Optional[ScreeningAiReviewPromptBuilder] = None,
        guard: Optional[ScreeningAiReviewGuard] = None,
    ) -> None:
        self.llm_client = llm_client or get_analyzer()
        self.prompt_builder = prompt_builder or ScreeningAiReviewPromptBuilder()
        self.guard = guard or ScreeningAiReviewGuard()

    def review_candidate(self, candidate: CandidateDecision) -> ScreeningAiReviewResult:
        prompt = self.prompt_builder.build(candidate)
        model_name = getattr(self.llm_client, "model_name", None)
        last_text: Optional[str] = None
        invalid_json_count = 0

        for attempt in range(2):
            try:
                raw_text = self.llm_client.generate_text(prompt, max_tokens=1200, temperature=0.1)
            except TimeoutError:
                return build_rules_fallback_review(
                    candidate,
                    "timeout",
                    prompt_version=SCREENING_AI_REVIEW_PROMPT_VERSION,
                    model_name=model_name,
                    parse_status="timeout",
                    retry_count=attempt,
                )
            except Exception:
                return build_rules_fallback_review(
                    candidate,
                    "timeout",
                    prompt_version=SCREENING_AI_REVIEW_PROMPT_VERSION,
                    model_name=model_name,
                    parse_status="exception",
                    retry_count=attempt,
                )

            last_text = raw_text if isinstance(raw_text, str) else None
            payload = _extract_json_payload(last_text or "")
            if payload is None:
                invalid_json_count += 1
                continue

            try:
                review = normalize_screening_ai_review_payload(payload)
            except ValueError:
                return build_rules_fallback_review(
                    candidate,
                    "normalize_failed",
                    prompt_version=SCREENING_AI_REVIEW_PROMPT_VERSION,
                    model_name=model_name,
                    parse_status="normalize_failed",
                    retry_count=attempt,
                    raw_model_output=last_text,
                )

            review.prompt_version = SCREENING_AI_REVIEW_PROMPT_VERSION
            review.model_name = model_name
            review.parse_status = "parsed"
            review.retry_count = attempt
            review.raw_model_output = last_text
            return self.guard.apply(candidate, review)

        return build_rules_fallback_review(
            candidate,
            "invalid_json",
            prompt_version=SCREENING_AI_REVIEW_PROMPT_VERSION,
            model_name=model_name,
            parse_status="invalid_json",
            retry_count=max(0, invalid_json_count - 1),
            raw_model_output=last_text,
        )


def _extract_json_payload(text: str) -> Optional[dict]:
    if not text:
        return None

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(1))
            if isinstance(payload, dict):
                return payload
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    return None
