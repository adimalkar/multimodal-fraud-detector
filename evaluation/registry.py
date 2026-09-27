"""Validate a local, rights-cleared evaluation registry before model calls."""

from __future__ import annotations

import hashlib
import argparse
import json
from dataclasses import dataclass
from pathlib import Path

MEDIA_TYPES = {"image", "video", "pdf"}
LABELS = {"authentic", "fully_generated", "locally_edited", "face_manipulated", "field_tampered"}
SPLITS = {"pilot", "validation", "test"}
RIGHTS = {"consented", "public_license"}


@dataclass(frozen=True)
class EvidenceItem:
    item_id: str
    relative_path: str
    sha256: str
    media_type: str
    label: str
    split: str
    source_group: str
    rights: str
    rights_reference: str
    generator_family: str | None
    parent_id: str | None
    transformations: tuple[str, ...]


def _nonempty_string(value: object, name: str, line: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Line {line}: {name} must be a nonempty string")
    return value.strip()


def load_registry(manifest: Path, data_root: Path, *, verify_files: bool = True) -> list[EvidenceItem]:
    """Load JSONL and reject missing rights, duplicate IDs, and source leakage."""
    root = data_root.resolve(strict=True)
    items: list[EvidenceItem] = []
    seen_ids: set[str] = set()
    source_splits: dict[str, str] = {}
    hash_splits: dict[str, str] = {}
    generator_splits: dict[str, str] = {}
    with manifest.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Line {line_number}: invalid JSON") from error
            if not isinstance(raw, dict):
                raise ValueError(f"Line {line_number}: expected an object")
            item_id = _nonempty_string(raw.get("item_id"), "item_id", line_number)
            if item_id in seen_ids:
                raise ValueError(f"Line {line_number}: duplicate item_id {item_id}")
            seen_ids.add(item_id)
            relative_path = _nonempty_string(raw.get("relative_path"), "relative_path", line_number)
            file_path = (root / relative_path).resolve()
            if not file_path.is_relative_to(root):
                raise ValueError(f"Line {line_number}: evidence path escapes data root")
            sha256 = _nonempty_string(raw.get("sha256"), "sha256", line_number).lower()
            if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
                raise ValueError(f"Line {line_number}: invalid SHA-256")
            media_type = _nonempty_string(raw.get("media_type"), "media_type", line_number)
            label = _nonempty_string(raw.get("label"), "label", line_number)
            split = _nonempty_string(raw.get("split"), "split", line_number)
            rights = _nonempty_string(raw.get("rights"), "rights", line_number)
            source_group = _nonempty_string(raw.get("source_group"), "source_group", line_number)
            rights_reference = _nonempty_string(
                raw.get("rights_reference"), "rights_reference", line_number
            )
            for name, value, allowed in (
                ("media_type", media_type, MEDIA_TYPES),
                ("label", label, LABELS),
                ("split", split, SPLITS),
                ("rights", rights, RIGHTS),
            ):
                if value not in allowed:
                    raise ValueError(f"Line {line_number}: unsupported {name}: {value}")
            if label == "fully_generated" and media_type == "pdf":
                raise ValueError(f"Line {line_number}: PDF needs a document-specific label")
            if label == "field_tampered" and media_type != "pdf":
                raise ValueError(f"Line {line_number}: field_tampered applies only to PDFs")
            if label in {"locally_edited", "face_manipulated"} and media_type == "pdf":
                raise ValueError(f"Line {line_number}: PDF needs a document-specific label")
            generator_family = raw.get("generator_family")
            if generator_family is not None:
                generator_family = _nonempty_string(generator_family, "generator_family", line_number)
            if label == "fully_generated" and not generator_family:
                raise ValueError(f"Line {line_number}: generated media needs generator_family")
            parent_id = raw.get("parent_id")
            if parent_id is not None:
                parent_id = _nonempty_string(parent_id, "parent_id", line_number)
                if parent_id == item_id:
                    raise ValueError(f"Line {line_number}: item cannot be its own parent")
            transformations = raw.get("transformations", [])
            if not isinstance(transformations, list) or any(
                not isinstance(value, str) or not value.strip() for value in transformations
            ):
                raise ValueError(f"Line {line_number}: transformations must be a list of strings")
            previous_split = source_splits.setdefault(source_group, split)
            if previous_split != split:
                raise ValueError(f"Line {line_number}: source_group crosses splits: {source_group}")
            previous_hash_split = hash_splits.setdefault(sha256, split)
            if previous_hash_split != split:
                raise ValueError(f"Line {line_number}: identical evidence crosses splits")
            if generator_family:
                previous_generator_split = generator_splits.setdefault(generator_family, split)
                if previous_generator_split != split:
                    raise ValueError(
                        f"Line {line_number}: generator_family crosses splits: {generator_family}"
                    )
            if verify_files:
                if not file_path.is_file():
                    raise ValueError(f"Line {line_number}: evidence file is missing")
                hasher = hashlib.sha256()
                with file_path.open("rb") as evidence_stream:
                    while chunk := evidence_stream.read(64 * 1024):
                        hasher.update(chunk)
                digest = hasher.hexdigest()
                if digest != sha256:
                    raise ValueError(f"Line {line_number}: SHA-256 mismatch for {item_id}")
            items.append(
                EvidenceItem(
                    item_id, relative_path, sha256, media_type, label, split,
                    source_group, rights, rights_reference, generator_family,
                    parent_id, tuple(transformations),
                )
            )
    if not items:
        raise ValueError("Registry has no evidence items")
    by_id = {item.item_id: item for item in items}
    for item in items:
        if item.parent_id:
            parent = by_id.get(item.parent_id)
            if parent is None:
                raise ValueError(f"Missing parent_id {item.parent_id} for {item.item_id}")
            if parent.source_group != item.source_group or parent.split != item.split:
                raise ValueError(f"Parent and derived item must share source_group and split: {item.item_id}")
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    items = load_registry(args.manifest, args.data_root)
    counts: dict[str, int] = {}
    for item in items:
        key = f"{item.split}:{item.media_type}:{item.label}"
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"items": len(items), "counts": counts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
