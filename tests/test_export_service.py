"""Tests for export_service.py — manifest filtering, validation, file copy, and trainer configs.

TDD: tests written before implementation (RED phase).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    project_dir: Path,
    *,
    images: list[dict] | None = None,
    active_profile: str = "sd15",
    anchor_word: str = "sks",
) -> Path:
    """Write a minimal manifest.json to project_dir/.klippbok/."""
    klippbok_dir = project_dir / ".klippbok"
    klippbok_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "1",
        "created": "2026-01-01T00:00:00+00:00",
        "updated": "2026-01-01T00:00:00+00:00",
        "active_profile": active_profile,
        "anchor_word": anchor_word,
        "images": images or [],
    }
    path = klippbok_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _crop_entry(path: str, caption: str = "1girl, blonde hair") -> dict:
    return {"path": path, "source": "crop", "caption": caption, "width": 512, "height": 768}


def _import_entry(path: str) -> dict:
    return {"path": path, "source": "import", "caption": "raw", "width": 1024, "height": 1024}


# ---------------------------------------------------------------------------
# Task 1: get_export_candidates
# ---------------------------------------------------------------------------


class TestGetExportCandidates:
    def test_returns_only_crop_entries(self, tmp_path: Path) -> None:
        _make_manifest(
            tmp_path,
            images=[
                _crop_entry("crop/a.jpg"),
                _import_entry("import/b.jpg"),
                _crop_entry("crop/c.jpg"),
            ],
        )
        from klippbok.services.export_service import get_export_candidates

        result = get_export_candidates(tmp_path)
        assert len(result) == 2
        assert all(e["source"] == "crop" for e in result)

    def test_returns_empty_when_no_manifest(self, tmp_path: Path) -> None:
        from klippbok.services.export_service import get_export_candidates

        result = get_export_candidates(tmp_path)
        assert result == []

    def test_returns_empty_when_no_crop_entries(self, tmp_path: Path) -> None:
        _make_manifest(tmp_path, images=[_import_entry("import/b.jpg")])
        from klippbok.services.export_service import get_export_candidates

        result = get_export_candidates(tmp_path)
        assert result == []

    def test_returns_empty_when_images_key_missing(self, tmp_path: Path) -> None:
        klippbok_dir = tmp_path / ".klippbok"
        klippbok_dir.mkdir(parents=True, exist_ok=True)
        manifest = {"version": "1", "created": "x", "updated": "x"}
        (klippbok_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        from klippbok.services.export_service import get_export_candidates

        result = get_export_candidates(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Task 1: validate_export_candidates
# ---------------------------------------------------------------------------


class TestValidateExportCandidates:
    def test_returns_empty_when_all_valid(self) -> None:
        from klippbok.services.export_service import validate_export_candidates

        entries = [
            _crop_entry("a.jpg", "1girl, smile"),
            _crop_entry("b.jpg", "1boy, looking at viewer"),
        ]
        issues = validate_export_candidates(entries)
        assert issues == []

    def test_detects_missing_caption_key(self) -> None:
        from klippbok.services.export_service import validate_export_candidates

        entries = [{"path": "a.jpg", "source": "crop", "width": 512, "height": 512}]
        issues = validate_export_candidates(entries)
        assert len(issues) == 1
        assert issues[0]["path"] == "a.jpg"
        assert issues[0]["issue"] == "missing_caption"

    def test_detects_empty_caption(self) -> None:
        from klippbok.services.export_service import validate_export_candidates

        entries = [_crop_entry("a.jpg", "   ")]  # whitespace only
        issues = validate_export_candidates(entries)
        assert len(issues) == 1
        assert issues[0]["path"] == "a.jpg"
        assert issues[0]["issue"] == "empty_caption"

    def test_detects_empty_string_caption(self) -> None:
        from klippbok.services.export_service import validate_export_candidates

        entries = [_crop_entry("a.jpg", "")]
        issues = validate_export_candidates(entries)
        assert len(issues) == 1
        assert issues[0]["issue"] == "empty_caption"

    def test_multiple_issues(self) -> None:
        from klippbok.services.export_service import validate_export_candidates

        entries = [
            _crop_entry("good.jpg", "valid caption"),
            {"path": "missing.jpg", "source": "crop"},
            _crop_entry("empty.jpg", ""),
        ]
        issues = validate_export_candidates(entries)
        assert len(issues) == 2
        paths = {i["path"] for i in issues}
        assert "missing.jpg" in paths
        assert "empty.jpg" in paths


# ---------------------------------------------------------------------------
# Task 1: ExportConfig
# ---------------------------------------------------------------------------


class TestExportConfig:
    def test_default_values(self, tmp_path: Path) -> None:
        from klippbok.services.export_service import ExportConfig

        cfg = ExportConfig(output_dir=tmp_path)
        assert cfg.trainer == "kohya"
        assert cfg.repeats == 5
        assert cfg.trigger_word == "sks"
        assert cfg.class_name == "person"
        assert cfg.concept_name == ""

    def test_custom_values(self, tmp_path: Path) -> None:
        from klippbok.services.export_service import ExportConfig

        cfg = ExportConfig(
            trainer="aitoolkit",
            repeats=10,
            trigger_word="mychar",
            class_name="woman",
            concept_name="MyCharacter",
            output_dir=tmp_path / "export",
        )
        assert cfg.trainer == "aitoolkit"
        assert cfg.repeats == 10
        assert cfg.trigger_word == "mychar"


# ---------------------------------------------------------------------------
# Task 1: get_export_defaults
# ---------------------------------------------------------------------------


class TestGetExportDefaults:
    def test_returns_resolution_from_profile(self, tmp_path: Path) -> None:
        _make_manifest(tmp_path, active_profile="sd15", anchor_word="jane")
        from klippbok.services.export_service import get_export_defaults

        defaults = get_export_defaults(tmp_path)
        assert defaults["resolution"] == 512  # SD1.5 base_resolution
        assert defaults["trigger_word"] == "jane"
        assert defaults["class_name"] == "person"
        assert defaults["default_repeats"] == 5

    def test_concept_name_from_project_folder(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        _make_manifest(project_dir, active_profile="sd15")
        from klippbok.services.export_service import get_export_defaults

        defaults = get_export_defaults(project_dir)
        assert defaults["concept_name"] == "my_project"

    def test_fallback_when_no_manifest(self, tmp_path: Path) -> None:
        from klippbok.services.export_service import get_export_defaults

        defaults = get_export_defaults(tmp_path)
        assert "resolution" in defaults
        assert defaults["default_repeats"] == 5


# ---------------------------------------------------------------------------
# Task 1: _copy_images_with_captions
# ---------------------------------------------------------------------------


class TestCopyImagesWithCaptions:
    def _make_image_files(self, project_dir: Path, paths: list[str]) -> None:
        for rel_path in paths:
            full = project_dir / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)  # minimal fake JPEG header

    def test_copies_image_and_writes_txt(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        self._make_image_files(project_dir, ["crop/a.jpg"])

        entries = [_crop_entry("crop/a.jpg", "1girl, smile")]
        from klippbok.services.export_service import _copy_images_with_captions

        count = _copy_images_with_captions(entries, project_dir, dest_dir, None)
        assert count == 1
        assert (dest_dir / "a.jpg").exists()
        assert (dest_dir / "a.txt").read_text(encoding="utf-8") == "1girl, smile"

    def test_writes_empty_txt_when_no_caption(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        self._make_image_files(project_dir, ["crop/b.png"])

        entries = [{"path": "crop/b.png", "source": "crop", "width": 512, "height": 512}]
        from klippbok.services.export_service import _copy_images_with_captions

        count = _copy_images_with_captions(entries, project_dir, dest_dir, None)
        assert count == 1
        assert (dest_dir / "b.txt").read_text(encoding="utf-8") == ""

    def test_calls_progress_callback(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        self._make_image_files(project_dir, ["crop/c.jpg", "crop/d.jpg"])

        entries = [
            _crop_entry("crop/c.jpg", "caption c"),
            _crop_entry("crop/d.jpg", "caption d"),
        ]
        calls: list[tuple[int, int]] = []

        def cb(current: int, total: int) -> None:
            calls.append((current, total))

        from klippbok.services.export_service import _copy_images_with_captions

        _copy_images_with_captions(entries, project_dir, dest_dir, cb)
        assert len(calls) == 2
        assert calls[0] == (1, 2)
        assert calls[1] == (2, 2)


# ---------------------------------------------------------------------------
# Task 2: generate_kohya_export
# ---------------------------------------------------------------------------


class TestGenerateKohyaExport:
    def _setup(self, tmp_path: Path) -> tuple[Path, Path, list[dict]]:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        output_dir = tmp_path / "export"
        output_dir.mkdir()
        images = ["crop/img1.jpg", "crop/img2.jpg"]
        for img in images:
            p = project_dir / img
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
        entries = [_crop_entry(img, f"caption for {img}") for img in images]
        return project_dir, output_dir, entries

    def test_creates_correct_folder_structure(self, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_kohya_export

        config = ExportConfig(
            trainer="kohya",
            repeats=5,
            trigger_word="sks",
            class_name="person",
            output_dir=output_dir,
        )
        generate_kohya_export(entries, project_dir, config, None)
        folder = output_dir / "5_sks person"
        assert folder.exists()
        assert (folder / "img1.jpg").exists()
        assert (folder / "img2.jpg").exists()
        assert (folder / "img1.txt").exists()
        assert (folder / "img2.txt").exists()

    def test_writes_kohya_toml(self, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_kohya_export

        config = ExportConfig(
            trainer="kohya", repeats=5, trigger_word="sks", class_name="person", output_dir=output_dir
        )
        result_path = generate_kohya_export(entries, project_dir, config, None)
        toml_path = output_dir / "kohya_config.toml"
        assert toml_path.exists()
        assert result_path == toml_path

        content = toml_path.read_text(encoding="utf-8")
        assert "[general]" in content
        assert "[[datasets]]" in content
        assert "[[datasets.subsets]]" in content
        assert "5_sks person" in content
        assert "num_repeats = 5" in content

    def test_toml_uses_forward_slashes(self, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_kohya_export

        config = ExportConfig(
            trainer="kohya", repeats=3, trigger_word="jane", class_name="woman", output_dir=output_dir
        )
        generate_kohya_export(entries, project_dir, config, None)
        content = (output_dir / "kohya_config.toml").read_text(encoding="utf-8")
        assert "\\" not in content

    def test_caption_written_from_manifest(self, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_kohya_export

        config = ExportConfig(
            trainer="kohya", repeats=5, trigger_word="sks", class_name="person", output_dir=output_dir
        )
        generate_kohya_export(entries, project_dir, config, None)
        folder = output_dir / "5_sks person"
        txt = (folder / "img1.txt").read_text(encoding="utf-8")
        assert txt == "caption for crop/img1.jpg"


# ---------------------------------------------------------------------------
# Task 2: generate_aitoolkit_export
# ---------------------------------------------------------------------------


class TestGenerateAiToolkitExport:
    def _setup(self, tmp_path: Path) -> tuple[Path, Path, list[dict]]:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        output_dir = tmp_path / "export"
        output_dir.mkdir()
        img_path = project_dir / "crop" / "img1.jpg"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
        entries = [_crop_entry("crop/img1.jpg", "my caption")]
        return project_dir, output_dir, entries

    def test_creates_images_folder(self, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_aitoolkit_export

        config = ExportConfig(trainer="aitoolkit", output_dir=output_dir)
        generate_aitoolkit_export(entries, project_dir, config, None)
        assert (output_dir / "images").exists()
        assert (output_dir / "images" / "img1.jpg").exists()
        assert (output_dir / "images" / "img1.txt").exists()

    def test_writes_yaml_config(self, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_aitoolkit_export

        config = ExportConfig(trainer="aitoolkit", output_dir=output_dir)
        result_path = generate_aitoolkit_export(entries, project_dir, config, None)
        yaml_path = output_dir / "aitoolkit_config.yaml"
        assert yaml_path.exists()
        assert result_path == yaml_path

        content = yaml_path.read_text(encoding="utf-8")
        assert "datasets:" in content
        assert "folder_path" in content
        assert "./images" in content
        assert "caption_ext:" in content and "txt" in content

    def test_yaml_has_no_is_video_field(self, tmp_path: Path) -> None:
        """Image exports must NOT have is_video in YAML (video-only field)."""
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_aitoolkit_export

        config = ExportConfig(trainer="aitoolkit", output_dir=output_dir)
        generate_aitoolkit_export(entries, project_dir, config, None)
        content = (output_dir / "aitoolkit_config.yaml").read_text(encoding="utf-8")
        assert "is_video" not in content

    def test_yaml_uses_forward_slashes(self, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_aitoolkit_export

        config = ExportConfig(trainer="aitoolkit", output_dir=output_dir)
        generate_aitoolkit_export(entries, project_dir, config, None)
        content = (output_dir / "aitoolkit_config.yaml").read_text(encoding="utf-8")
        assert "\\" not in content


# ---------------------------------------------------------------------------
# Task 2: generate_onetrainer_export
# ---------------------------------------------------------------------------


@patch(
    "klippbok.services.export_service._load_onetrainer_base_preset",
    return_value={"__version": 3, "resolution": "512"},
)
class TestGenerateOneTrainerExport:
    def _setup(self, tmp_path: Path) -> tuple[Path, Path, list[dict]]:
        project_dir = tmp_path / "mycharacter"
        project_dir.mkdir()
        output_dir = tmp_path / "export"
        output_dir.mkdir()
        img_path = project_dir / "crop" / "img1.jpg"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
        entries = [_crop_entry("crop/img1.jpg", "1girl, smile")]
        return project_dir, output_dir, entries

    def test_creates_workspace_directory_structure(self, _mock: MagicMock, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_onetrainer_export

        config = ExportConfig(
            trainer="onetrainer", concept_name="MyChar", output_dir=output_dir
        )
        generate_onetrainer_export(entries, project_dir, config, None)
        # Workspace directories
        assert (output_dir / "dataset" / "images").exists()
        assert (output_dir / "training_concepts").exists()
        assert (output_dir / "training_samples").exists()
        assert (output_dir / "cache").exists()
        assert (output_dir / "output").exists()
        assert (output_dir / "backup").exists()
        assert (output_dir / "save").exists()
        assert (output_dir / "samples").exists()
        assert (output_dir / "tensorboard").exists()
        assert (output_dir / "config").exists()
        # Images land in dataset/images/
        assert (output_dir / "dataset" / "images" / "img1.jpg").exists()

    def test_writes_concept_json_v2_schema(self, _mock: MagicMock, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_onetrainer_export

        config = ExportConfig(
            trainer="onetrainer", concept_name="MyChar", repeats=7, output_dir=output_dir
        )
        concept_path, preset_path = generate_onetrainer_export(entries, project_dir, config, None)
        assert concept_path == output_dir / "training_concepts" / "MyChar.json"
        assert concept_path.exists()

        data = json.loads(concept_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1
        concept = data[0]
        assert concept["__version"] == 2
        assert concept["name"] == "MyChar"
        assert concept["type"] == "STANDARD"
        assert "/" in concept["path"]  # forward slashes
        # v2 schema: balancing is float, balancing_strategy is the enum
        assert concept["balancing"] == 7.0
        assert isinstance(concept["balancing"], float)
        assert concept["balancing_strategy"] == "REPEATS"
        # image_variations and text_variations are ints, not arrays
        assert concept["image_variations"] == 1
        assert isinstance(concept["image_variations"], int)
        assert concept["text_variations"] == 1
        # image and text sub-objects exist
        assert "image" in concept
        assert concept["image"]["__version"] == 0
        assert "text" in concept
        assert concept["text"]["__version"] == 0
        assert concept["text"]["prompt_source"] == "sample"
        assert concept["loss_weight"] == 1.0
        assert concept["include_subdirectories"] is False

    def test_concept_json_has_prompt_source_in_text(self, _mock: MagicMock, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_onetrainer_export

        config = ExportConfig(trainer="onetrainer", concept_name="Test", output_dir=output_dir)
        generate_onetrainer_export(entries, project_dir, config, None)
        concept_path = output_dir / "training_concepts" / "Test.json"
        data = json.loads(concept_path.read_text(encoding="utf-8"))
        concept = data[0]
        assert concept["text"]["prompt_source"] == "sample"

    def test_writes_training_preset_json(self, _mock: MagicMock, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_onetrainer_export

        config = ExportConfig(trainer="onetrainer", concept_name="MyChar", output_dir=output_dir)
        concept_path, preset_path = generate_onetrainer_export(entries, project_dir, config, None)
        assert preset_path == output_dir / "config" / "training_preset.json"
        assert preset_path.exists()

        data = json.loads(preset_path.read_text(encoding="utf-8"))
        assert "concept_file_name" in data
        assert "output_model_destination" in data
        # workspace_dir and cache_dir must be set
        assert "workspace_dir" in data
        assert "cache_dir" in data
        # concept_file_name should be relative (not absolute)
        assert not data["concept_file_name"].startswith("/")
        assert not data["concept_file_name"].startswith("C:")
        assert data["concept_file_name"] == "training_concepts/MyChar.json"
        # resolution must be a string
        assert isinstance(data["resolution"], str)

    def test_concept_path_uses_forward_slashes(self, _mock: MagicMock, tmp_path: Path) -> None:
        project_dir, output_dir, entries = self._setup(tmp_path)
        from klippbok.services.export_service import ExportConfig, generate_onetrainer_export

        config = ExportConfig(trainer="onetrainer", concept_name="MyChar", output_dir=output_dir)
        generate_onetrainer_export(entries, project_dir, config, None)
        concept_path = output_dir / "training_concepts" / "MyChar.json"
        data = json.loads(concept_path.read_text(encoding="utf-8"))
        assert "\\" not in data[0]["path"]


# ---------------------------------------------------------------------------
# Task 2: perform_export
# ---------------------------------------------------------------------------


class TestPerformExport:
    def _setup_project(self, tmp_path: Path) -> tuple[Path, list[dict]]:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        img_path = project_dir / "crop" / "img1.jpg"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
        _make_manifest(project_dir, images=[_crop_entry("crop/img1.jpg", "test caption")])
        return project_dir, [_crop_entry("crop/img1.jpg", "test caption")]

    def test_performs_kohya_export(self, tmp_path: Path) -> None:
        project_dir, _ = self._setup_project(tmp_path)
        output_dir = tmp_path / "export"
        from klippbok.services.export_service import ExportConfig, ExportResult, perform_export

        config = ExportConfig(trainer="kohya", output_dir=output_dir)
        result = perform_export(project_dir, config, None)
        assert isinstance(result, ExportResult)
        assert result.status == "ok"
        assert result.image_count == 1
        assert result.config_path.exists()

    def test_performs_aitoolkit_export(self, tmp_path: Path) -> None:
        project_dir, _ = self._setup_project(tmp_path)
        output_dir = tmp_path / "export"
        from klippbok.services.export_service import ExportConfig, ExportResult, perform_export

        config = ExportConfig(trainer="aitoolkit", output_dir=output_dir)
        result = perform_export(project_dir, config, None)
        assert result.status == "ok"
        assert result.image_count == 1

    @patch(
        "klippbok.services.export_service._load_onetrainer_base_preset",
        return_value={"__version": 3, "resolution": "512"},
    )
    def test_performs_onetrainer_export(self, _mock: MagicMock, tmp_path: Path) -> None:
        project_dir, _ = self._setup_project(tmp_path)
        output_dir = tmp_path / "export"
        from klippbok.services.export_service import ExportConfig, ExportResult, perform_export

        config = ExportConfig(trainer="onetrainer", concept_name="TestChar", output_dir=output_dir)
        result = perform_export(project_dir, config, None)
        assert result.status == "ok"
        assert result.image_count == 1
        assert result.preset_path is not None
        assert result.preset_path.exists()

    def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        project_dir, _ = self._setup_project(tmp_path)
        output_dir = tmp_path / "deep" / "nested" / "export"
        from klippbok.services.export_service import ExportConfig, perform_export

        config = ExportConfig(trainer="kohya", output_dir=output_dir)
        result = perform_export(project_dir, config, None)
        assert output_dir.exists()
        assert result.status == "ok"

    def test_result_output_dir_matches_config(self, tmp_path: Path) -> None:
        project_dir, _ = self._setup_project(tmp_path)
        output_dir = tmp_path / "myexport"
        from klippbok.services.export_service import ExportConfig, perform_export

        config = ExportConfig(trainer="kohya", output_dir=output_dir)
        result = perform_export(project_dir, config, None)
        assert result.output_dir == output_dir
