"""JoyCaption subprocess detection and execution.

Finds an existing JoyCaption installation by checking common install paths
and the JOYCAPTION_PATH environment variable, then runs captioning via
subprocess in JoyCaption's own venv.

JoyCaption runs as a subprocess in its own venv (unlike VLM backends which
use API calls). The model is loaded once per batch and processes all images
sequentially, emitting JSON-lines progress to stdout.

Pattern mirrors detect_seedvr2() in klippbok/services/upscale_service.py.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Inline JoyCaption runner script
# ---------------------------------------------------------------------------
# This script is written to a temp file and executed using JoyCaption's venv
# Python. It loads the model once, processes all images, and emits JSON-lines
# to stdout so the parent process can track progress.

_JOYCAPTION_RUNNER_SCRIPT = r'''
"""Inline JoyCaption runner -- invoked as subprocess by klippbok."""
import gc
import json
import sys
from pathlib import Path

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="JSON file with image paths")
    parser.add_argument("--trigger", default="", help="Trigger word to prepend")
    args = parser.parse_args()

    manifest_data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    image_paths = manifest_data["images"]
    total = len(image_paths)

    if total == 0:
        print(json.dumps({"type": "done", "total": 0}), flush=True)
        return

    # Import heavy deps only after arg parsing
    import torch
    from PIL import Image
    from transformers import AutoProcessor, LlavaForConditionalGeneration, BitsAndBytesConfig

    MODEL_PATH = "fancyfeast/llama-joycaption-beta-one-hf-llava"
    CAPTION_PROMPT = "Write a list of Booru-like tags for this image."
    REMOVE_TAGS = [
        "watermark", "signature", "text", "logo", "username",
        "photograph", "photo",
    ]

    print(json.dumps({"type": "status", "message": "Loading JoyCaption model..."}), flush=True)

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        llm_int8_skip_modules=["vision_tower", "multi_modal_projector"],
    )

    processor = AutoProcessor.from_pretrained(MODEL_PATH)
    model = LlavaForConditionalGeneration.from_pretrained(
        MODEL_PATH,
        quantization_config=quantization_config,
        device_map={"": 0},
        torch_dtype=torch.float16,
    )
    model.eval()

    if hasattr(model, "vision_tower") and model.vision_tower is not None:
        model.vision_tower = model.vision_tower.to(torch.float16)

    print(json.dumps({"type": "status", "message": "Model loaded, starting captioning..."}), flush=True)

    for i, img_path_str in enumerate(image_paths):
        img_path = Path(img_path_str)
        try:
            image = Image.open(img_path).convert("RGB")

            convo = [
                {"role": "system", "content": "You are a helpful image captioner."},
                {"role": "user", "content": CAPTION_PROMPT},
            ]
            convo_string = processor.tokenizer.apply_chat_template(
                convo, tokenize=False, add_generation_prompt=True
            )
            inputs = processor(
                text=[convo_string], images=[image], return_tensors="pt"
            ).to("cuda:0")

            if "pixel_values" in inputs:
                inputs["pixel_values"] = inputs["pixel_values"].to(torch.float16)

            with torch.no_grad():
                generate_ids = model.generate(
                    **inputs,
                    max_new_tokens=100,
                    do_sample=True,
                    suppress_tokens=None,
                    use_cache=True,
                    temperature=0.6,
                    top_k=None,
                    top_p=0.9,
                )[0]

            generate_ids = generate_ids[inputs["input_ids"].shape[1]:]
            caption = processor.tokenizer.decode(
                generate_ids, skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            ).strip()

            # Clean caption
            caption = caption.lower().strip()
            prefixes = [
                "here are the booru-like tags for the image:",
                "here are the booru-like tags:",
                "here is a list of booru-like tags:",
                "booru-like tags:", "tags:",
            ]
            for prefix in prefixes:
                if caption.startswith(prefix):
                    caption = caption[len(prefix):].strip()
            caption = caption.strip(".:;,!?\"'")

            tags = [tag.strip() for tag in caption.split(",")]
            tags = [tag for tag in tags if tag and len(tag) > 1]
            tags = [tag for tag in tags if not any(r in tag for r in REMOVE_TAGS)]

            seen = set()
            unique_tags = []
            for tag in tags:
                if tag not in seen:
                    seen.add(tag)
                    unique_tags.append(tag)

            final_tags = []
            trigger = args.trigger
            if trigger:
                final_tags.append(trigger)
            final_tags.extend(
                t for t in unique_tags if t.lower() not in [f.lower() for f in final_tags]
            )
            caption = ", ".join(final_tags)

            del inputs, generate_ids
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            print(json.dumps({
                "type": "caption",
                "index": i,
                "total": total,
                "path": img_path_str,
                "caption": caption,
            }), flush=True)

        except Exception as e:
            print(json.dumps({
                "type": "error",
                "index": i,
                "total": total,
                "path": img_path_str,
                "error": str(e),
            }), flush=True)

    print(json.dumps({"type": "done", "total": total}), flush=True)


if __name__ == "__main__":
    main()
'''


def _build_joycaption_paths() -> list[Path]:
    """Build the list of candidate JoyCaption paths to check."""
    candidates: list[Path] = [
        Path(r"C:\GenAI\Tools\JoyCaption"),
        Path.home() / "GenAI" / "Tools" / "JoyCaption",
    ]
    env_path = os.environ.get("JOYCAPTION_PATH")
    if env_path:
        candidates.append(Path(env_path))
    return candidates


# Module-level list (can be patched in tests — mirrors _SEEDVR2_COMMON_PATHS pattern)
_JOYCAPTION_COMMON_PATHS: list[Path] = _build_joycaption_paths()


def detect_joycaption() -> Path | None:
    """Find a JoyCaption installation at known paths.

    Checks each candidate path for the presence of a Python executable in
    the venv:
    - venv/Scripts/python.exe (Windows)
    - venv/bin/python (Linux/macOS)

    Also checks the JOYCAPTION_PATH environment variable (included in
    _JOYCAPTION_COMMON_PATHS at module load time via _build_joycaption_paths).

    Returns:
        Root directory of the JoyCaption installation, or None if not found.
    """
    for candidate in _JOYCAPTION_COMMON_PATHS:
        if not candidate:
            continue
        # Support both Windows (Scripts) and Linux/macOS (bin) venv layouts
        python_candidates = [
            candidate / "venv" / "Scripts" / "python.exe",  # Windows
            candidate / "venv" / "bin" / "python",           # Linux/macOS
        ]

        if any(p.is_file() for p in python_candidates):
            logger.debug("Found JoyCaption installation at: %s", candidate)
            return candidate

    logger.debug("JoyCaption not found at any of: %s", _JOYCAPTION_COMMON_PATHS)
    return None


def get_venv_python(joycaption_root: Path) -> Path:
    """Get the Python executable path for JoyCaption's venv.

    Args:
        joycaption_root: Root directory of the JoyCaption installation.

    Returns:
        Path to the venv's Python executable.

    Raises:
        FileNotFoundError: If no Python executable is found in the venv.
    """
    if platform.system() == "Windows":
        python_path = joycaption_root / "venv" / "Scripts" / "python.exe"
    else:
        python_path = joycaption_root / "venv" / "bin" / "python"

    if not python_path.is_file():
        raise FileNotFoundError(
            f"JoyCaption venv Python not found at {python_path}"
        )
    return python_path


def run_joycaption_image(
    joycaption_root: Path,
    image_paths: list[Path],
    trigger_word: str = "",
) -> subprocess.Popen:
    """Launch JoyCaption as a subprocess to caption a batch of images.

    Writes the inline runner script to a temp file and executes it using
    JoyCaption's venv Python. The subprocess emits JSON-lines to stdout
    for progress tracking.

    The caller is responsible for reading stdout and calling proc.wait().

    Args:
        joycaption_root: Root directory of the JoyCaption installation.
        image_paths: List of absolute paths to images to caption.
        trigger_word: Optional trigger word to prepend to captions.

    Returns:
        subprocess.Popen instance with stdout=PIPE (line-buffered JSON-lines).

    Raises:
        FileNotFoundError: If JoyCaption venv Python is not found.
    """
    python_path = get_venv_python(joycaption_root)

    # Write runner script to a temp file
    script_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_joycaption_runner.py",
        delete=False,
        encoding="utf-8",
    )
    script_file.write(_JOYCAPTION_RUNNER_SCRIPT)
    script_file.close()

    # Write manifest file with image paths
    manifest_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_joycaption_manifest.json",
        delete=False,
        encoding="utf-8",
    )
    manifest_data = {"images": [str(p) for p in image_paths]}
    json.dump(manifest_data, manifest_file)
    manifest_file.close()

    cmd = [
        str(python_path),
        script_file.name,
        "--manifest", manifest_file.name,
    ]
    if trigger_word:
        cmd.extend(["--trigger", trigger_word])

    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}

    logger.info(
        "Launching JoyCaption subprocess: %d images, trigger=%r",
        len(image_paths), trigger_word,
    )

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=str(joycaption_root),
        encoding="utf-8",
        errors="replace",
    )
    return proc
