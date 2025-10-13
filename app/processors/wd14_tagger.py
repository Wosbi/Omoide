from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable

import numpy as np
from cv2.typing import MatLike
from PIL import Image, ImageOps
from PIL.ImageFile import ImageFile
from sqlmodel import Session, select

from app.api.tags import attach_tag_to_media, get_or_create_tag
from app.config import settings
from app.logger import logger
from app.models import Media, MediaTagLink, Scene, Tag
from app.processors.base import MediaProcessor


@dataclass(frozen=True, slots=True)
class _TagDefinition:
    index: int
    name: str
    category: str


class WD14Tagger(MediaProcessor):
    name = "wd14_tagger"
    order = 35

    def __init__(self) -> None:
        self._ort_session = None
        self._ort_input = None
        self._pending: list[tuple[Media, np.ndarray]] = []
        self._tag_definitions: list[_TagDefinition] = []
        self._category_thresholds: dict[str, tuple[bool, float]] = {}
        self._batch_size: int = 1
        self._max_tags: int = 0
        self._processed_items: int = 0
        self._total_tags_assigned: int = 0
        self._score_sum: float = 0.0
        self._score_count: int = 0
        self._min_dimension: int = 64
        self._summary_logged: bool = False

    def load_model(self):
        cfg = getattr(settings.tagging, "wd14", None)
        if not cfg or not cfg.enabled:
            logger.info("WD14Tagger disabled via settings; skipping load.")
            self.active = False
            return

        try:
            import onnxruntime as ort
        except Exception as exc:  # pragma: no cover - import guard
            logger.warning("WD14Tagger: failed to import onnxruntime: %s", exc)
            self.active = False
            return

        model_path = self._resolve_model_path(cfg.model_path)
        labels_path = self._resolve_labels_path(cfg.labels_path)
        if not model_path or not labels_path:
            logger.warning(
                "WD14Tagger: model or labels missing (model=%s, labels=%s); disabling",
                model_path,
                labels_path,
            )
            self.active = False
            return

        try:
            self._ort_session = ort.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.exception("WD14Tagger: failed to initialize model at %s", model_path)
            self.active = False
            return

        inputs = self._ort_session.get_inputs()
        if not inputs:
            logger.error("WD14Tagger: model inputs missing; disabling")
            self.active = False
            return
        self._ort_input = inputs[0].name

        try:
            self._tag_definitions = self._load_tag_definitions(labels_path)
        except Exception as exc:  # pragma: no cover - guard
            logger.exception("WD14Tagger: failed to read labels from %s", labels_path)
            self.active = False
            return

        self._category_thresholds = {
            "general": (cfg.general.enabled, float(cfg.general.threshold)),
            "character": (cfg.character.enabled, float(cfg.character.threshold)),
            "copyright": (cfg.copyright.enabled, float(cfg.copyright.threshold)),
            "rating": (cfg.rating.enabled, float(cfg.rating.threshold)),
        }
        self._batch_size = max(1, int(cfg.batch_size or 1))
        self._max_tags = max(0, int(cfg.max_tags or 0))
        self._summary_logged = False
        self.active = True
        logger.info(
            "WD14Tagger ready (model=%s, labels=%s, batch=%s, max_tags=%s)",
            model_path,
            labels_path,
            self._batch_size,
            self._max_tags,
        )

    def unload(self):
        self._log_summary()
        self._ort_session = None
        self._ort_input = None
        self._pending.clear()
        self._tag_definitions = []
        self._category_thresholds = {}
        self._batch_size = 1
        self._max_tags = 0
        self._processed_items = 0
        self._total_tags_assigned = 0
        self._score_sum = 0.0
        self._score_count = 0
        self._summary_logged = False

    def process(
        self,
        media: Media,
        session: Session,
        scenes: list[tuple[Scene, MatLike]] | list[ImageFile] | list[Scene],
    ) -> bool | None:
        if not self.active or not self._ort_session:
            return True

        if self._has_existing_wd14_tags(media, session):
            media.ran_auto_tagging = True
            session.add(media)
            return True

        if not scenes:
            return True

        if not self._is_media_size_valid(media):
            logger.debug(
                "WD14Tagger: skipping %s due to tiny dimensions (%sx%s)",
                media.path,
                media.width,
                media.height,
            )
            media.ran_auto_tagging = True
            session.add(media)
            return True

        image = self._extract_primary_image(scenes)
        if image is None:
            logger.debug("WD14Tagger: no image data available for %s", media.path)
            media.ran_auto_tagging = True
            session.add(media)
            return True

        tensor = self._prepare_tensor(image)
        if tensor is None:
            logger.debug("WD14Tagger: failed to prepare tensor for %s", media.path)
            media.ran_auto_tagging = True
            session.add(media)
            return True

        self._pending.append((media, tensor))
        self._flush_queue(session, force=len(self._pending) >= self._batch_size)
        return True

    # ----- Internal helpers -------------------------------------------------

    def finalize(self, session: Session) -> None:
        if not self.active or not self._ort_session:
            self._log_summary()
            return
        self._flush_queue(session, force=True)
        self._log_summary()

    def _flush_queue(self, session: Session, force: bool) -> None:
        if not self._pending:
            return
        if not force and len(self._pending) < self._batch_size:
            return

        medias, tensors = zip(*self._pending)
        batch = np.concatenate(tensors, axis=0)
        try:
            outputs = self._ort_session.run(None, {self._ort_input: batch})
        except Exception:
            logger.exception("WD14Tagger: inference failed; clearing pending queue")
            self._pending.clear()
            return

        scores = outputs[0]
        if scores.shape[0] != len(medias):
            logger.error(
                "WD14Tagger: batch output mismatch (%s != %s)",
                scores.shape[0],
                len(medias),
            )
            self._pending.clear()
            return

        for media_obj, prediction in zip(medias, scores):
            self._handle_predictions(media_obj, prediction, session)

        self._pending.clear()

    def _handle_predictions(
        self, media: Media, prediction: Iterable[float], session: Session
    ) -> None:
        scored_tags = []
        for tag_def, score in zip(self._tag_definitions, prediction):
            category = tag_def.category
            enabled, threshold = self._category_thresholds.get(category, (False, 1.0))
            if not enabled:
                continue
            if float(score) < threshold:
                continue
            scored_tags.append((tag_def.name, float(score), category))

        if not scored_tags:
            logger.debug("WD14Tagger: no tags above threshold for %s", media.path)
            media.ran_auto_tagging = True
            session.add(media)
            self._processed_items += 1
            return

        scored_tags.sort(key=lambda item: item[1], reverse=True)
        if self._max_tags:
            scored_tags = scored_tags[: self._max_tags]

        formatted = [
            (f"wd14:{name}|{score:.2f}", score)
            for name, score, _ in scored_tags
        ]
        scores_only = [score for _, score in formatted]

        for tag_name, score in formatted:
            tag = get_or_create_tag(tag_name, session)
            attach_tag_to_media(media.id, tag.id, session, score=score)

        media.ran_auto_tagging = True
        session.add(media)

        self._processed_items += 1
        self._total_tags_assigned += len(formatted)
        self._score_sum += sum(scores_only)
        self._score_count += len(scores_only)

        mean_score = mean(scores_only) if scores_only else 0.0

        logger.info(
            "WD14Tagger: assigned %s tags to %s (mean score %.3f)",
            len(formatted),
            media.filename,
            mean_score,
        )

    def _has_existing_wd14_tags(self, media: Media, session: Session) -> bool:
        existing = session.exec(
            select(Tag.id)
            .join(MediaTagLink, MediaTagLink.tag_id == Tag.id)
            .where(
                MediaTagLink.media_id == media.id,
                Tag.name.like("wd14:%"),
            )
        ).first()
        if existing:
            logger.debug(
                "WD14Tagger: existing WD14 tags found for %s; skipping", media.path
            )
            return True
        return False

    def _extract_primary_image(
        self, scenes: list[tuple[Scene, MatLike]] | list[ImageFile] | list[Scene]
    ) -> Image.Image | None:
        if not scenes:
            return None

        for candidate in scenes:
            if isinstance(candidate, ImageFile):
                try:
                    return candidate.convert("RGB")
                except Exception:
                    continue
            if isinstance(candidate, Image.Image):
                try:
                    return candidate.convert("RGB")
                except Exception:
                    continue
            if isinstance(candidate, tuple) and len(candidate) == 2:
                frame = candidate[1]
                try:
                    return Image.fromarray(frame).convert("RGB")
                except Exception:
                    continue
            if isinstance(candidate, Scene):
                thumb_rel = candidate.thumbnail_path
                if not thumb_rel:
                    continue
                thumb_path = settings.general.thumb_dir / thumb_rel
                try:
                    with Image.open(thumb_path) as thumb_img:
                        return ImageOps.exif_transpose(thumb_img).convert("RGB")
                except FileNotFoundError:
                    logger.debug(
                        "WD14Tagger: thumbnail missing for scene %s", thumb_path
                    )
                except Exception:
                    logger.debug(
                        "WD14Tagger: failed to load thumbnail %s", thumb_path
                    )
                continue
        return None

    def _prepare_tensor(self, image: Image.Image) -> np.ndarray | None:
        try:
            resized = image.resize((448, 448), Image.BICUBIC)
        except Exception:
            return None
        arr = np.asarray(resized, dtype=np.float32)
        if arr.ndim != 3 or arr.shape[2] != 3:
            return None
        arr = arr / 255.0
        arr = np.transpose(arr, (2, 0, 1))
        arr = (arr - 0.5) / 0.5
        return arr[np.newaxis, ...]

    def _load_tag_definitions(self, path: Path) -> list[_TagDefinition]:
        results: list[_TagDefinition] = []
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader):
                name = row.get("name") or row.get("tag")
                category = self._normalize_category(row.get("category"))
                if not name or not category:
                    continue
                results.append(
                    _TagDefinition(index=idx, name=name, category=category)
                )
        if not results:
            raise RuntimeError("WD14Tagger: no tag definitions loaded")
        return results

    def _normalize_category(self, category: str | None) -> str:
        if category is None:
            return "general"
        value = str(category).strip().lower()
        mapping = {
            "0": "general",
            "1": "general",
            "2": "copyright",
            "3": "character",
            "4": "character",
            "5": "general",
            "6": "general",
            "7": "general",
            "8": "general",
            "9": "rating",
            "general": "general",
            "character": "character",
            "copyright": "copyright",
            "rating": "rating",
        }
        return mapping.get(value, value or "general")

    def _log_summary(self) -> None:
        if self._summary_logged or not self._processed_items:
            return
        avg_tags = (
            self._total_tags_assigned / self._processed_items
            if self._processed_items
            else 0.0
        )
        mean_score = (
            self._score_sum / self._score_count if self._score_count else 0.0
        )
        logger.info(
            "WD14Tagger summary: %s media, avg tags %.2f, mean score %.3f",
            self._processed_items,
            avg_tags,
            mean_score,
        )
        self._summary_logged = True

    def _resolve_model_path(self, configured: str | None) -> Path | None:
        candidates: list[Path] = []
        base_dir = settings.general.models_dir / "wd14"
        if configured:
            candidates.append(self._coerce_path(configured))
        candidates.append(base_dir / "model.onnx")
        candidates.append(base_dir / "wd-v1-4-convnext-tagger-v2.onnx")
        candidates.extend(base_dir.glob("*.onnx"))
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return None

    def _resolve_labels_path(self, configured: str | None) -> Path | None:
        candidates: list[Path] = []
        base_dir = settings.general.models_dir / "wd14"
        if configured:
            candidates.append(self._coerce_path(configured))
        candidates.append(base_dir / "selected_tags.csv")
        candidates.extend(base_dir.glob("*.csv"))
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return None

    def _coerce_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = settings.general.models_dir / path
        return path

    def _is_media_size_valid(self, media: Media) -> bool:
        if media.width and media.height:
            return min(media.width, media.height) >= self._min_dimension
        return True
