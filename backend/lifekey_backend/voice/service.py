import typing

from pydantic import ValidationError

from ..brain import prompts
from ..brain.core import AIOutputInvalid, Brain, NoProviderAvailable
from ..schemas import DictationOut


class VoiceService:
    def __init__(self, brain: Brain):
        self.brain = brain

    async def cleanup(
        self,
        raw_text: str,
        language: str | None,
        style: str,
        stt_engine: str,
    ) -> dict[str, typing.Any]:
        result: dict[str, typing.Any] = {
            "raw_text": raw_text,
            "language": language,
            "stt_engine": stt_engine,
            "style": style,
            "cleanup_status": "done",
            "clean_text": None,
            "summary": None,
            "key_points": [],
            "to_do": [],
            "slang_translated": [],
            "unclear": [],
            "provider": None,
            "model": None,
        }
        if not raw_text.strip():
            result["cleanup_status"] = "empty"
            return result

        try:
            data, provider, model = await self.brain.extract(
                "dictation",
                prompts.build_dictation_user(raw_text, style, language),
                prompts.DICTATION_SCHEMA,
            )
            cleaned = DictationOut.model_validate(data)
        except NoProviderAvailable:
            result["cleanup_status"] = "ai_offline"
            return result
        except (AIOutputInvalid, ValidationError):
            result["cleanup_status"] = "ai_invalid"
            return result

        result.update(
            clean_text=cleaned.clean_text.strip(),
            summary=cleaned.summary.strip(),
            key_points=cleaned.key_points[:50],
            to_do=cleaned.to_do[:50],
            slang_translated=[
                item.model_dump() for item in cleaned.slang_translated[:50]
            ],
            unclear=cleaned.unclear[:50],
            provider=provider,
            model=model,
        )
        return result
