"""media/video_generator.py — Veo 3.1 video generation (v4 — timeout cap + better errors)."""
import os, json, re, time, subprocess, requests, logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("VideoGenerator")

# Maximum polling iterations (60 × 20s = 20 min cap)
DEFAULT_MAX_POLLS = 60


@dataclass
class VideoResult:
    idea_index:    int
    scene_index:   int
    generation_id: str
    status:        str
    video_url:     Optional[str] = None
    error:         Optional[str] = None


def parse_llm_json(raw):
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if match:
        raw = match.group(1)
    else:
        start = raw.find("{"); end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end + 1]
    raw = raw.strip()

    def fix_string_newlines(text):
        result = []; i = 0; in_str = False
        while i < len(text):
            ch = text[i]
            if in_str and ch == "\\" and i + 1 < len(text):
                result.append(ch); result.append(text[i + 1]); i += 2; continue
            if ch == '"': in_str = not in_str; result.append(ch)
            elif in_str and ch in ("\n", "\r"): result.append(" ")
            else: result.append(ch)
            i += 1
        return "".join(result)

    raw = fix_string_newlines(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json
        return json.loads(repair_json(cleaned))
    except Exception:
        pass
    raise ValueError(f"Could not parse JSON from LLM output.\nFirst 300 chars:\n{raw[:300]}")


class VeoPromptBuilder:
    @staticmethod
    def _build_character_text(character: dict, anchor: str = "") -> str:
        if anchor: return anchor
        if not character: return ""
        parts = []
        for key in ("gender","age","skin","hair","eye_color","facial_details","physical_details","outfit"):
            val = character.get(key) or character.get(key.replace("_"," "))
            if val: parts.append(str(val))
        if not parts: return ""
        description = ", ".join(parts)
        expr = character.get("facial_expression","")
        return (f"CHARACTER ANCHOR — this exact person appears in EVERY scene: {description}. "
                f"The character's face, hair, skin tone, build, and outfit are IDENTICAL across all scenes. "
                f"{'Current expression: '+expr+'. ' if expr else ''}"
                f"This is the same continuous person throughout the entire video.")

    @staticmethod
    def _build_image_ref_hint(is_first_scene: bool) -> str:
        if is_first_scene:
            return ("Use the provided reference image as the exact visual anchor for this video. "
                    "Match its subject, appearance, color palette, and style precisely in every scene.")
        return ("Maintain perfect visual consistency with the reference image provided. "
                "The subject, environment style, and color palette must remain identical to scene 1.")

    @staticmethod
    def _build_lighting(lighting: dict) -> str:
        if not lighting: return ""
        parts = []
        for k, label in [("camera_angle","camera angle"),("camera_type","camera"),
                          ("lighting_mode","lighting"),("lighting_position","light position"),
                          ("camera_movement","movement")]:
            val = lighting.get(k) or lighting.get(k.replace("_"," "))
            if val: parts.append(f"{label}: {val}")
        return "Cinematography — " + ", ".join(parts) + "." if parts else ""

    @staticmethod
    def _build_voiceover_style(vo_props: dict, language: str, voiceover_text: str) -> str:
        if not voiceover_text: return ""
        gender = (vo_props or {}).get("gender","Female")
        tone   = (vo_props or {}).get("tone","confident")
        return (f'Voiceover: {gender or "Female"} voice, {tone or "confident"} tone, '
                f'speaking in {language}: "{voiceover_text}".')

    @classmethod
    def build(cls, scene, hook, cta, visual_direction, brand_colors, language,
              image_url="", character=None, character_anchor="", style_anchor="",
              lighting=None, vo_props=None, is_first_scene=False, is_last_scene=False):
        visual_direction = visual_direction or {}
        visuals      = scene.get("visuals","")
        voiceover    = scene.get("voiceover","")
        text_overlay = scene.get("text_overlay","")
        pacing       = visual_direction.get("pacing","medium")
        transitions  = visual_direction.get("transitions","cut")
        color_notes  = visual_direction.get("color_usage","")
        brand_color  = brand_colors[0] if brand_colors else "#FF0000"

        has_image  = bool(image_url and image_url.strip())
        char_block = (cls._build_image_ref_hint(is_first_scene) if has_image
                      else cls._build_character_text(character or {}, anchor=character_anchor))

        if style_anchor and not is_first_scene:
            lighting_block = f"[LOCKED STYLE from scene 1] {style_anchor}"
        else:
            lighting_block = cls._build_lighting(lighting or {})

        vo_block   = cls._build_voiceover_style(vo_props or {}, language, voiceover)
        hook_block = (f'OPENING HOOK ({hook.get("duration_seconds",3)}s): bold on-screen text reads '
                      f'"{hook.get("text","")}" — eye-catching, high contrast, centered.'
                      if is_first_scene and hook else "")
        cta_block  = (f'END CALL-TO-ACTION: overlay text "{cta.get("text","")}" '
                      f'appears at {cta.get("placement","end")} of video.'
                      if is_last_scene and cta else "")
        visual_block  = f"Scene visuals: {visuals}."
        overlay_block = f'On-screen text overlay: "{text_overlay}".' if text_overlay else ""
        style_block   = (f"Brand color {brand_color} used. {color_notes} "
                         f"Pacing: {pacing}. Transitions: {transitions}. "
                         f"Vertical 9:16 format, professional social-media quality.")

        flat = " ".join(filter(None, [char_block,lighting_block,hook_block,visual_block,
                                       vo_block,overlay_block,cta_block,style_block])).strip()
        return flat, {"flat_prompt":flat,"scene":scene.get("scene",1)}


class VideoJoiner:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.concat_dir = os.path.join(output_dir,"concat")
        os.makedirs(self.concat_dir, exist_ok=True)

    @staticmethod
    def _ffmpeg_available():
        try:
            subprocess.run(["ffmpeg","-version"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _write_concat_list(self, scene_paths, idea_idx):
        list_path = os.path.join(self.concat_dir, f"idea_{idea_idx+1}_concat.txt")
        with open(list_path,"w",encoding="utf-8") as f:
            for path in scene_paths:
                f.write(f"file '{os.path.abspath(path).replace(chr(92),'/')}'\n")
        return list_path

    def _run_ffmpeg(self, list_path, output_path):
        # Try stream copy first (fast)
        result = subprocess.run(
            ["ffmpeg","-y","-f","concat","-safe","0","-i",list_path,"-c","copy",output_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        if result.returncode == 0:
            return True

        logger.warning("FFmpeg copy codec failed, attempting re-encode with libx264")
        # Re-encode fallback
        result = subprocess.run(
            ["ffmpeg","-y","-f","concat","-safe","0","-i",list_path,
             "-c:v","libx264","-preset","fast","-crf","18",
             "-c:a","aac","-b:a","192k","-movflags","+faststart",output_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        if result.returncode != 0:
            logger.error("FFmpeg re-encode also failed: %s", result.stderr.decode("utf-8","replace")[:500])
            return False
        return True

    def join(self, scene_paths, idea_idx):
        valid = [p for p in scene_paths if p and os.path.isfile(p)]
        if len(valid) == 0: return None
        if len(valid) == 1: return valid[0]
        if not self._ffmpeg_available():
            logger.warning("FFmpeg not available — cannot join %d scenes", len(valid))
            return None
        output_path = os.path.join(self.output_dir, f"idea_{idea_idx+1}_full.mp4")
        list_path   = self._write_concat_list(valid, idea_idx)
        if not self._run_ffmpeg(list_path, output_path):
            return None
        return output_path


class VideoGenerator:
    MODEL    = "google/veo-3.1-i2v"
    BASE_URL = "https://api.aimlapi.com/v2"

    def __init__(self, api_key, image_url, language="Egyptian Arabic", brand_colors=None,
                 aspect_ratio="9:16", poll_interval=20, output_dir="output_videos",
                 model=None, max_polls=DEFAULT_MAX_POLLS):
        self.api_key      = api_key
        self.image_url    = image_url or ""
        self.language     = language
        self.brand_colors = brand_colors or [None]
        self.aspect_ratio = aspect_ratio
        self.poll_interval= poll_interval
        self.output_dir   = output_dir
        self.video_model  = model or self.MODEL
        self.max_polls    = max_polls
        os.makedirs(output_dir, exist_ok=True)
        self.joiner = VideoJoiner(output_dir)

    def _headers(self):
        return {"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"}

    def _submit(self, prompt: str) -> Optional[str]:
        payload = {"model":self.video_model,"prompt":prompt,"aspect_ratio":self.aspect_ratio}
        if self.image_url:
            payload["image_url"] = self.image_url
        try:
            resp = requests.post(f"{self.BASE_URL}/video/generations",
                                 json=payload, headers=self._headers(), timeout=60)
            if resp.status_code >= 400:
                logger.error("Submit error %d: %s", resp.status_code, resp.text[:200])
                return None
            return resp.json().get("id")
        except requests.RequestException as e:
            logger.error("Submit request failed: %s", e)
            return None

    def _poll(self, gen_id: str) -> tuple[Optional[str], Optional[str]]:
        """Returns (video_url, error_message). Enforces max_polls timeout cap."""
        logger.info("Polling %s (max %d × %ds = %d min)", gen_id,
                    self.max_polls, self.poll_interval,
                    self.max_polls * self.poll_interval // 60)
        polls = 0
        while polls < self.max_polls:
            time.sleep(self.poll_interval)
            polls += 1
            try:
                resp = requests.get(f"{self.BASE_URL}/video/generations",
                                    params={"generation_id":gen_id},
                                    headers=self._headers(), timeout=30)
                if resp.status_code >= 400:
                    err = f"Poll HTTP {resp.status_code}: {resp.text[:100]}"
                    logger.error(err)
                    return None, err
                data   = resp.json()
                status = data.get("status","")
                if status == "completed":
                    return data.get("video",{}).get("url"), None
                elif status in ("failed","error"):
                    err = data.get("error","Generation failed")
                    logger.error("Generation %s failed: %s", gen_id, err)
                    return None, str(err)
            except requests.RequestException as e:
                logger.warning("Poll request failed: %s", e)

        timeout_err = f"Timed out after {self.max_polls} polls ({self.max_polls*self.poll_interval}s)"
        logger.error("Generation %s %s", gen_id, timeout_err)
        return None, timeout_err

    def _download(self, url: str, filename: str) -> str:
        path = os.path.join(self.output_dir, filename)
        try:
            resp = requests.get(url, timeout=120)
            with open(path,"wb") as f: f.write(resp.content)
            return path
        except requests.RequestException as e:
            logger.error("Download failed: %s", e)
            return url

    @staticmethod
    def _safe_get(idea, *keys, default=None):
        for key in keys:
            val = idea.get(key)
            if val is not None and val != {} and val != []: return val
        return default if default is not None else {}

    @staticmethod
    def _merge_scene_delta(scene, prev_scene):
        if not prev_scene: return scene
        merged = dict(prev_scene); merged.update(scene)
        if scene.get("use_character") is False:
            merged.pop("character_details",None); return merged
        for key in ("character_details","lighting_conditions","visual_direction"):
            prev_val = prev_scene.get(key) or {}; curr_val = scene.get(key) or {}
            if prev_val or curr_val: merged[key] = {**prev_val,**curr_val}
        return merged

    def _save_idea_json(self, idea, idea_idx, scenes):
        caption  = idea.get("caption","")
        hashtags = idea.get("hashtags",[])
        if isinstance(caption,list): caption = " ".join(str(c) for c in caption)
        idea_data = {"idea_index":idea_idx+1,"caption":str(caption),"hashtags":hashtags,
                     "hook":idea.get("hook",{}),"cta":idea.get("cta",{}),
                     "script":idea.get("script",[]),
                     "generated_scenes":[s for s in scenes if s.get("status")=="completed"]}
        json_path = os.path.join(self.output_dir,f"idea_{idea_idx+1}.json")
        with open(json_path,"w",encoding="utf-8") as f:
            json.dump(idea_data,f,ensure_ascii=False,indent=2)
        return json_path

    def generate_all(self, content_json: dict) -> list[VideoResult]:
        ideas   = content_json.get("ideas",[])
        results = []
        builder = VeoPromptBuilder()
        idea_scene_paths: dict = {}
        has_image = bool(self.image_url and self.image_url.strip())

        for idea_idx, idea in enumerate(ideas):
            hook             = idea.get("hook",{})
            script           = idea.get("script",[])
            cta              = idea.get("cta",{})
            n_scenes         = len(script)
            visual_direction = self._safe_get(idea,"visual_direction","visual direction")
            character        = self._safe_get(idea,"character_details","charachter details","character details")
            lighting         = self._safe_get(idea,"lighting_conditions","Lighting condition ","Lighting condition")
            vo_props         = self._safe_get(idea,"voiceover_properties","Voice over property","voiceover_props")

            scenes_output: list = []
            prev_scene:    dict = {}
            idea_scene_paths[idea_idx] = []
            character_anchor = ""; style_anchor = ""

            for scene_idx, scene in enumerate(script):
                is_first = scene_idx == 0; is_last = scene_idx == n_scenes - 1
                scene_num   = scene.get("scene", scene_idx+1)
                full_scene  = self._merge_scene_delta(scene, prev_scene)
                prev_scene  = full_scene
                scene_character = full_scene.get("character_details") or character or {}
                scene_lighting  = full_scene.get("lighting_conditions") or lighting or {}

                if is_first and not has_image:
                    character_anchor = VeoPromptBuilder._build_character_text(scene_character)
                    style_parts = []
                    if scene_lighting: style_parts.append(VeoPromptBuilder._build_lighting(scene_lighting))
                    vd = visual_direction or {}
                    if vd.get("pacing"): style_parts.append(f"pacing: {vd['pacing']}")
                    style_anchor = " | ".join(filter(None,style_parts))

                prompt, _ = builder.build(
                    scene=full_scene, hook=hook, cta=cta, visual_direction=visual_direction,
                    brand_colors=self.brand_colors, language=self.language, image_url=self.image_url,
                    character=scene_character, character_anchor=character_anchor,
                    style_anchor=style_anchor, lighting=scene_lighting, vo_props=vo_props,
                    is_first_scene=is_first, is_last_scene=is_last
                )

                gen_id = self._submit(prompt)
                if not gen_id:
                    err = "Submission to AIML API failed"
                    scenes_output.append({"scene":scene_num,"status":"failed","error":err})
                    results.append(VideoResult(idea_index=idea_idx,scene_index=scene_idx,
                                               generation_id="",status="failed",error=err))
                    continue

                video_url, poll_error = self._poll(gen_id)
                if not video_url:
                    err = poll_error or "Generation failed"
                    scenes_output.append({"scene":scene_num,"status":"failed","generation_id":gen_id,"error":err})
                    results.append(VideoResult(idea_index=idea_idx,scene_index=scene_idx,
                                               generation_id=gen_id,status="failed",error=err))
                    continue

                filename   = f"idea{idea_idx+1}_scene{scene_num}.mp4"
                local_path = self._download(video_url, filename)
                scenes_output.append({"scene":scene_num,"status":"completed","generation_id":gen_id,"video_path":local_path})
                results.append(VideoResult(idea_index=idea_idx,scene_index=scene_idx,
                                           generation_id=gen_id,status="completed",video_url=local_path))
                idea_scene_paths[idea_idx].append(local_path)

            json_path       = self._save_idea_json(idea, idea_idx, scenes_output)
            full_video_path = self.joiner.join(idea_scene_paths[idea_idx], idea_idx)
            if full_video_path:
                try:
                    with open(json_path,"r") as f: d = json.load(f)
                    d["full_video_path"] = full_video_path
                    with open(json_path,"w") as f: json.dump(d,f,ensure_ascii=False,indent=2)
                except Exception: pass

        done   = [r for r in results if r.status=="completed"]
        failed = [r for r in results if r.status=="failed"]
        logger.info("Video generation summary: %d completed, %d failed", len(done), len(failed))
        return results
