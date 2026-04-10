"""media/static_post.py — Gemini image generation (v4 — proper error surfacing)."""
import base64, logging, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("StaticPost")


@dataclass
class PostResult:
    idea_index:   int
    status:       str   # "completed" | "partial" | "failed"
    image_path:   Optional[str] = None
    image_url:    Optional[str] = None
    error:        Optional[str] = None  # now always populated on failure


class StaticPostGenerator:
    """Generate static social posts via Gemini image API."""

    MAX_CONCURRENT = 5
    DEFAULT_MODEL  = "gemini-3.1-flash-image-preview"

    def __init__(self, api_key: str, output_dir: str, model: str = DEFAULT_MODEL):
        self.api_key    = api_key
        self.output_dir = Path(output_dir)
        self.model      = model or self.DEFAULT_MODEL
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Internal ───────────────────────────────────────────────────────────────
    def _build_prompt(self, idea: dict, brand_color: str, language: str) -> str:
        hook      = idea.get("hook", "")
        copy_     = idea.get("post_copy", "") or idea.get("caption", "")
        img_desc  = idea.get("image_description", "")
        visual    = idea.get("visual_style", "")
        hashtags  = " ".join(f"#{h.strip('#')}" for h in (idea.get("hashtags") or [])[:5])

        parts = [
            f"Create a high-quality, professional social media static post image.",
            f"Brand color: {brand_color}.",
            f"Language: {language}.",
        ]
        if img_desc:
            parts.append(f"Image description: {img_desc}.")
        if visual:
            parts.append(f"Visual style: {visual}.")
        if hook:
            parts.append(f"Main headline / hook text (if included in image): {hook}.")
        if copy_:
            parts.append(f"Supporting copy (if space): {copy_[:200]}.")
        if hashtags:
            parts.append(f"Hashtags (small text at bottom if shown): {hashtags}.")
        parts += [
            "Aspect ratio: 4:5 (portrait, Instagram optimal).",
            "Style: modern, bold, eye-catching, scroll-stopping.",
            "No stock photo clichés. High production value.",
        ]
        return " ".join(parts)

    def _generate_image(self, prompt: str, filename: str) -> tuple[Optional[str], Optional[str]]:
        """Returns (path, error_message). error_message is None on success."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model  = genai.GenerativeModel(self.model)
            result = model.generate_content(
                contents=[prompt],
                generation_config=genai.GenerationConfig(
                    response_modalities=["IMAGE", "TEXT"]
                ),
            )

            for part in result.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    ext        = part.inline_data.mime_type.split("/")[-1].replace("jpeg","jpg")
                    img_path   = self.output_dir / f"{filename}.{ext}"
                    img_path.write_bytes(base64.b64decode(part.inline_data.data))
                    logger.info("Image saved: %s", img_path)
                    return str(img_path), None

            return None, "Gemini returned no image part in response"

        except Exception as e:
            err_msg = f"Image generation error: {e}"
            logger.error(err_msg)
            return None, err_msg

    def _process_idea(self, idea: dict, idea_idx: int,
                       brand_color: str, language: str) -> PostResult:
        filename = f"idea_{idea_idx + 1}"
        prompt   = self._build_prompt(idea, brand_color, language)

        for attempt in range(2):  # one retry
            path, err = self._generate_image(prompt, filename)
            if path:
                return PostResult(idea_index=idea_idx, status="completed", image_path=path)
            if attempt == 0:
                logger.warning("Image attempt 1 failed for idea %d: %s — retrying", idea_idx + 1, err)
                time.sleep(2)

        # Both attempts failed — return partial with actual error message
        return PostResult(idea_index=idea_idx, status="partial", error=err)

    # ── Public ─────────────────────────────────────────────────────────────────
    def generate_all(self, content_json: dict, brand_colors: list,
                     language: str = "English") -> list[PostResult]:
        ideas       = content_json.get("ideas", [])
        brand_color = (brand_colors or ["#4f8ef7"])[0] or "#4f8ef7"
        results: list[PostResult] = []

        with ThreadPoolExecutor(max_workers=min(self.MAX_CONCURRENT, len(ideas) or 1)) as pool:
            futures = {
                pool.submit(self._process_idea, idea, i, brand_color, language): i
                for i, idea in enumerate(ideas)
            }
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as e:
                    idx = futures[fut]
                    err = f"Unexpected error processing idea {idx + 1}: {e}"
                    logger.error(err)
                    results.append(PostResult(idea_index=idx, status="failed", error=err))

        results.sort(key=lambda r: r.idea_index)

        completed = [r for r in results if r.status == "completed"]
        failed    = [r for r in results if r.status != "completed"]
        logger.info("Image generation: %d completed, %d failed/partial",
                    len(completed), len(failed))

        if failed:
            for r in failed:
                logger.warning("Idea %d: %s — %s", r.idea_index + 1, r.status, r.error)

        return results
