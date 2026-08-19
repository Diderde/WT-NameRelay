from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.models import (
    ConflictKind,
    ConflictPolicy,
    CrewGroupType,
    CrewNameGroup,
    ManualCopyMode,
    RadioStagedCopyPlan,
    RadioTargetOperation,
)
from app.services import AudioProcessingSourceAdapter, RadioManualSourceAdapter
from app.services.radio_staged_worker import DistributionFileCopyWorker


@dataclass(frozen=True)
class _AudioGroup:
    group_key: str
    base_name: str
    group_type: CrewGroupType
    module: str
    category: str
    names: tuple[str, ...]


class AverageDistributionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.members9 = tuple(
            f"pilot_contract_{bucket}_v{member}"
            for bucket in range(1, 4)
            for member in range(1, 4)
        )
        self.radio_group = CrewNameGroup(
            "pilot_contract", "pilot_contract", CrewGroupType.V_MATRIX_SUFFIX, self.members9
        )
        self.audio_group = _AudioGroup(
            "pilot_contract",
            "pilot_contract",
            CrewGroupType.V_MATRIX_SUFFIX,
            "radio",
            "information",
            self.members9,
        )
        self.radio_adapter = RadioManualSourceAdapter()
        self.audio_adapter = AudioProcessingSourceAdapter()

    def _group12(self):
        members = tuple(
            f"voice_contract_{bucket}_{member}"
            for bucket in range(4)
            for member in range(1, 4)
        )
        radio = CrewNameGroup(
            "voice_contract", "voice_contract", CrewGroupType.MATRIX_SUFFIX, members
        )
        audio = _AudioGroup(
            "voice_contract",
            "voice_contract",
            CrewGroupType.MATRIX_SUFFIX,
            "radio",
            "information",
            members,
        )
        return members, radio, audio

    def _write(self, directory: Path, indexes: tuple[int, ...], payloads: tuple[bytes, ...]) -> tuple[Path, ...]:
        paths = []
        for member_index, payload in zip(indexes, payloads, strict=True):
            path = directory / f"{self.members9[member_index]}.wav"
            path.write_bytes(payload)
            paths.append(path)
        return tuple(paths)

    @staticmethod
    def _owner(_name: str) -> str:
        return "pilot_contract"

    @staticmethod
    def _normalized(plan) -> tuple[tuple[str, int, str, str], ...]:
        return tuple(
            (
                operation.source.content_hash,
                operation.target_bucket_index,
                operation.target_member_name,
                operation.conflict_kind.value,
            )
            for operation in plan.operations
        )

    def _plans(self, directory: Path, sources: tuple[Path, ...]):
        radio = self.radio_adapter.build(self.radio_group, sources, directory, self._owner)
        audio = self.audio_adapter.build(self.audio_group, sources, directory, self._owner)
        self.assertEqual(self._normalized(radio), self._normalized(audio))
        return radio, audio

    def test_same_bucket_abc_is_identical_111222333_for_both_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0, 1, 2), (b"A", b"B", b"C"))
            radio, audio = self._plans(directory, paths)
            self.assertEqual(radio.final_pattern, "111222333")
            self.assertEqual(audio.final_pattern, "111222333")
            self.assertEqual(radio.source_target_count, 3)
            self.assertEqual(radio.generated_count, 6)

    def test_different_bucket_abc_is_111222333(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0, 3, 6), (b"A", b"B", b"C"))
            radio, _audio = self._plans(directory, paths)
            self.assertEqual(radio.final_pattern, "111222333")

    def test_two_sources_cycle_111222111(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0, 1), (b"A", b"B"))
            radio, _audio = self._plans(directory, paths)
            self.assertEqual(radio.final_pattern, "111222111")

    def test_complete_equal_hash_bucket_folds_to_one_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0, 1, 2), (b"same", b"same", b"same"))
            radio, _audio = self._plans(directory, paths)
            self.assertEqual(len(radio.sources), 1)
            self.assertEqual(radio.final_pattern, "111111111")

    def test_complete_different_hash_bucket_remains_three_sources(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0, 1, 2), (b"A", b"B", b"C"))
            radio, _audio = self._plans(directory, paths)
            self.assertEqual(len(radio.sources), 3)

    def test_source_targets_and_external_conflict_are_identical(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0,), (b"A",))
            (directory / f"{self.members9[3]}.wav").write_bytes(b"external")
            radio, _audio = self._plans(directory, paths)
            self.assertIs(radio.operations[0].conflict_kind, ConflictKind.SOURCE_TARGET)
            external = next(op for op in radio.operations if op.target_member_name == self.members9[3])
            self.assertIs(external.conflict_kind, ConflictKind.EXTERNAL_CONFLICT)

    def test_twelve_member_four_sources_is_111222333444_for_both(self) -> None:
        members, radio_group, audio_group = self._group12()
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            sources = []
            for index, payload in zip((0, 3, 6, 9), (b"A", b"B", b"C", b"D"), strict=True):
                path = directory / f"{members[index]}.wav"
                path.write_bytes(payload)
                sources.append(path)
            owner = lambda _name: "voice_contract"
            radio = self.radio_adapter.build(radio_group, sources, directory, owner)
            audio = self.audio_adapter.build(audio_group, sources, directory, owner)
            self.assertEqual(self._normalized(radio), self._normalized(audio))
            self.assertEqual(radio.final_pattern, "111222333444")

    def test_twelve_member_three_sources_is_111222333111_for_both(self) -> None:
        members, radio_group, audio_group = self._group12()
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            sources = []
            for index, payload in zip((0, 1, 2), (b"A", b"B", b"C"), strict=True):
                path = directory / f"{members[index]}.wav"
                path.write_bytes(payload)
                sources.append(path)
            owner = lambda _name: "voice_contract"
            radio = self.radio_adapter.build(radio_group, sources, directory, owner)
            audio = self.audio_adapter.build(audio_group, sources, directory, owner)
            self.assertEqual(self._normalized(radio), self._normalized(audio))
            self.assertEqual(radio.final_pattern, "111222333111")

    def test_more_independent_sources_than_buckets_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0, 1, 2, 3), (b"A", b"B", b"C", b"D"))
            with self.assertRaisesRegex(ValueError, "独立来源数"):
                self.radio_adapter.build(self.radio_group, paths, directory, self._owner)

    def test_shared_plan_executes_abc_as_three_hash_triplets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self._write(directory, (0, 1, 2), (b"audio-A", b"audio-B", b"audio-C"))
            plan, _audio = self._plans(directory, paths)
            operations = tuple(
                RadioTargetOperation(
                    module=operation.module,
                    group_id=operation.group_id,
                    group_display_name=operation.group_display_name,
                    source_original_path=operation.source.original_path,
                    source_snapshot_key=operation.source.source_id,
                    source_member_name=operation.source.canonical_basename,
                    target_member_name=operation.target_member_name,
                    target_path=operation.target_path,
                    copy_mode=ManualCopyMode.AVERAGE,
                    will_overwrite=operation.will_overwrite,
                    conflict_kind=operation.conflict_kind,
                    source_content_hash=operation.source.content_hash,
                )
                for operation in plan.operations
            )
            staged = RadioStagedCopyPlan(operations, imported_source_paths=plan.all_source_paths)
            worker = DistributionFileCopyWorker(
                staged, threading.Event(), ConflictPolicy.SKIP_EXISTING
            )
            worker.prepare()
            expected_hashes = [hashlib.sha256(payload).hexdigest() for payload in (b"audio-A", b"audio-B", b"audio-C")]
            actual = [
                hashlib.sha256((directory / f"{member}.wav").read_bytes()).hexdigest()
                for member in self.members9
            ]
            self.assertEqual(actual, expected_hashes[:1] * 3 + expected_hashes[1:2] * 3 + expected_hashes[2:] * 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
