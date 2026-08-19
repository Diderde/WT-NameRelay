from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.audio import (
    AudioProjectService,
    BlankClip,
    TimelineClipKind,
    TimelineEditKind,
    TimelineModel,
    WaveformEnvelope,
)
from app.audio.models import format_ms
from app.audio.project_service import CREW_CATEGORIES, RADIO_CATEGORIES
from app.main_window import MainWindow


class AudioProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_project_layout_and_unicode_category_paths(self) -> None:
        root = Path(tempfile.mkdtemp()) / "\u9879\u76ee"
        service = AudioProjectService()
        service.ensure_layout(root)
        for category in CREW_CATEGORIES:
            self.assertTrue((root / "\u8f66\u7ec4" / category).is_dir())
        for category in RADIO_CATEGORIES:
            self.assertTrue((root / "\u65e0\u7ebf\u7535" / category).is_dir())

    def test_target_parser_and_timeline_undo(self) -> None:
        self.assertEqual(AudioProjectService.parse_target(r"C:\a\voice_name.WAV"), "voice_name")
        model = TimelineModel()
        model.add_blank(duration=2.0)
        model.add_blank(duration=1.0)
        self.assertEqual(model.duration, 3.0)
        model.undo()
        self.assertEqual(model.duration, 2.0)
        model.redo()
        self.assertEqual(model.duration, 3.0)

    def test_millisecond_trim_is_non_destructive_and_undoable(self) -> None:
        root = Path(tempfile.mkdtemp())
        model = TimelineModel()
        clip = model.add_audio(root / "source.wav", 5.0)
        model.trim_ms(clip.clip_id, 1245, 4880)
        edited = model.items[0]
        self.assertEqual(edited.trim_start_ms, 1245)
        self.assertEqual(edited.effective_end_ms, 4880)
        self.assertEqual(format_ms(edited.duration_ms), "00:03.635")
        model.undo()
        self.assertEqual(model.items[0].trim_start_ms, 0)

    def test_audio_split_is_atomic_reuses_waveform_and_undoes_to_original(self) -> None:
        root = Path(tempfile.mkdtemp())
        model = TimelineModel()
        clip = model.add_audio(root / "source.wav", 4.0)
        waveform = WaveformEnvelope((((-0.5, 0.5),),), 48_000, 1)
        model.set_waveform(clip.clip_id, waveform)
        location = model.locate(1250)
        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.kind, TimelineClipKind.AUDIO)
        result = model.split_audio_at(clip.clip_id, 1250)
        self.assertEqual(len(model.items), 2)
        left, right = model.items
        self.assertNotEqual(left.clip_id, right.clip_id)
        self.assertEqual((left.trim_start_ms, left.effective_end_ms), (0, 1250))
        self.assertEqual((right.trim_start_ms, right.effective_end_ms), (1250, 4000))
        self.assertEqual(model.duration_ms, 4000)
        self.assertEqual(result.source_position_ms, 1250)
        self.assertIs(left.waveform, waveform)
        self.assertIs(right.waveform, waveform)
        undo = model.undo()
        self.assertIsNotNone(undo)
        assert undo is not None
        self.assertEqual(undo.kind, TimelineEditKind.SPLIT)
        self.assertEqual(model.items[0].clip_id, clip.clip_id)
        self.assertIs(model.items[0].waveform, waveform)

    def test_audio_split_rejects_boundaries_and_blank(self) -> None:
        root = Path(tempfile.mkdtemp())
        model = TimelineModel()
        audio = model.add_audio(root / "source.wav", 1.0)
        blank = model.add_blank(duration=2.0)
        with self.assertRaises(ValueError):
            model.split_audio_at(audio.clip_id, 0)
        with self.assertRaises(ValueError):
            model.split_audio_at(audio.clip_id, 1000)
        with self.assertRaises(ValueError):
            model.split_audio_at(blank.clip_id, 1500)
        self.assertEqual(len(model.items), 2)

    def test_home_has_audio_route_and_fifth_page(self) -> None:
        window = MainWindow()
        self.assertEqual(window.stack.count(), 5)
        self.assertEqual(len(window.home_page.cards), 4)
        window.close()
