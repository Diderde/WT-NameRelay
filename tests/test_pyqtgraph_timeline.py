from __future__ import annotations

import math
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractButton

from app.audio import (
    AudioExportService,
    AudioPreviewService,
    ExportSettings,
    FfmpegLocator,
    TimelineModel,
    WaveformCache,
    WaveformWorker,
)
from app.audio.models import TimelineClipKind
from app.pages.audio_processing_page import AudioProcessingPage, PlaybackState
from app.widgets.pyqtgraph_timeline import AdaptiveTimeAxisItem, PyQtGraphTimeline


def make_wav(path: Path, duration_ms: int, frequency: float = 440.0) -> Path:
    rate = 48_000
    frame_count = round(duration_ms * rate / 1000)
    frames = bytearray()
    for index in range(frame_count):
        value = round(math.sin(index * 2 * math.pi * frequency / rate) * 10_000)
        frames.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(frames)
    return path


class PyQtGraphTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _process_until(self, predicate, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_snapshot_is_single_source_for_trim_blank_and_total(self) -> None:
        source = make_wav(self.root / "source.wav", 3386)
        model = TimelineModel()
        clip = model.add_audio(source, 3.386)
        model.trim_ms(clip.clip_id, 425, 3120)
        model.add_blank(duration=2.0)
        snapshot = model.snapshot()
        self.assertEqual(snapshot.total_duration_ms, 4695)
        self.assertEqual(snapshot.clips[0].source_start_ms, 425)
        self.assertEqual(snapshot.clips[0].source_end_ms, 3120)
        self.assertEqual(snapshot.clips[1].kind, TimelineClipKind.BLANK)
        model.undo()
        self.assertEqual(model.snapshot().total_duration_ms, 2695)

    def test_axis_switches_units_and_keeps_major_labels_apart(self) -> None:
        axis = AdaptiveTimeAxisItem()
        levels = axis.tickValues(0, 0.8, 800)
        major_step = levels[0][0]
        self.assertGreaterEqual(major_step / 0.8 * 800, 80)
        labels = axis.tickStrings(levels[0][1], 1, major_step)
        self.assertTrue(all(label.endswith("ms") for label in labels))
        levels = axis.tickValues(0, 12, 800)
        labels = axis.tickStrings(levels[0][1], 1, levels[0][0])
        self.assertTrue(all(label.endswith("s") for label in labels))

    def test_left_fixed_zoom_reaches_one_pixel_per_millisecond(self) -> None:
        timeline = PyQtGraphTimeline()
        timeline.resize(900, 240)
        timeline.show()
        self.app.processEvents()
        timeline.view_box.setXRange(1.25, 5.25, padding=0)
        timeline.set_pixels_per_second(1000)
        self.app.processEvents()
        left, right = timeline.view_box.viewRange()[0]
        self.assertAlmostEqual(left, 1.25, places=3)
        self.assertEqual(timeline.pixels_per_second, 1000)
        self.assertLess(right - left, 1.0)
        timeline.close()

    def test_graphics_handles_commit_real_millisecond_trim(self) -> None:
        class Event:
            def __init__(self, local_x: float, scene_x: float) -> None:
                self._local = QPointF(local_x, 0.5)
                self._scene = QPointF(scene_x, 100)

            def pos(self) -> QPointF:
                return self._local

            def scenePos(self) -> QPointF:
                return self._scene

            def modifiers(self):
                return Qt.KeyboardModifier.NoModifier

            def accept(self) -> None:
                pass

        source = make_wav(self.root / "handles.wav", 3386)
        model = TimelineModel()
        clip = model.add_audio(source, 3.386)
        timeline = PyQtGraphTimeline()
        timeline.resize(1000, 250)
        timeline.show()
        timeline.set_timeline(model)
        timeline.set_pixels_per_second(1000)
        self.app.processEvents()
        item = timeline._clip_items[0]
        item.trim_committed.connect(model.trim_ms)
        item.mousePressEvent(Event(0.001, 50))
        item.mouseMoveEvent(Event(0.426, 475))
        item.mouseReleaseEvent(Event(0.426, 475))
        self.assertEqual(model.items[0].trim_start_ms, 425)
        self.assertEqual(model.items[0].effective_end_ms, 3386)
        timeline.set_timeline(model)
        item = timeline._clip_items[0]
        item.trim_committed.connect(model.trim_ms)
        item.mousePressEvent(Event(2.960, 800))
        item.mouseMoveEvent(Event(2.460, 300))
        item.mouseReleaseEvent(Event(2.460, 300))
        self.assertEqual(model.items[0].effective_end_ms, 2886)
        timeline.close()

    def test_waveform_worker_builds_multilevel_cache_and_reuses_it(self) -> None:
        source = make_wav(self.root / "wave.wav", 1000)
        received: list[tuple] = []
        worker = WaveformWorker("one", source)
        worker.finished.connect(lambda *args: received.append(args))
        worker.run()
        self.assertEqual(received[0][1], 1000)
        envelope = received[0][2]
        self.assertGreater(len(envelope.levels), 1)
        before = WaveformCache.hits
        cached: list[tuple] = []
        worker2 = WaveformWorker("two", source)
        worker2.finished.connect(lambda *args: cached.append(args))
        worker2.run()
        self.assertGreater(WaveformCache.hits, before)
        self.assertIs(cached[0][2], envelope)

    def test_exact_3386ms_preview_and_multi_clip_blank_use_snapshot(self) -> None:
        first = make_wav(self.root / "first.wav", 3386, 440)
        second = make_wav(self.root / "second.wav", 500, 660)
        model = TimelineModel()
        model.add_audio(first, 3.386)
        model.add_blank(duration=0.25)
        model.add_audio(second, 0.5)
        snapshot = model.snapshot()
        target = self.root / "preview.wav"
        results: list[tuple] = []
        worker = AudioPreviewService(
            snapshot,
            ExportSettings(),
            target,
            threading.Event(),
        )
        worker.finished.connect(lambda *args: results.append(args))
        worker.run()
        self.assertTrue(results and results[0][0], results)
        self.assertTrue(target.is_file())
        self.assertLessEqual(abs(FfmpegLocator.probe_duration_ms(target) - 4136), 5)

    def test_trimmed_preview_uses_effective_range(self) -> None:
        source = make_wav(self.root / "trim.wav", 3386)
        model = TimelineModel()
        clip = model.add_audio(source, 3.386)
        model.trim_ms(clip.clip_id, 425, 3120)
        target = self.root / "trimmed-preview.wav"
        results: list[tuple] = []
        worker = AudioPreviewService(
            model.snapshot(),
            ExportSettings(),
            target,
            threading.Event(),
        )
        worker.finished.connect(lambda *args: results.append(args))
        worker.run()
        self.assertTrue(results[0][0], results)
        self.assertLessEqual(abs(FfmpegLocator.probe_duration_ms(target) - 2695), 5)

    def test_qmedia_player_reaches_end_of_complete_3386ms_cache(self) -> None:
        source = make_wav(self.root / "full.wav", 3386)
        player = QMediaPlayer()
        output = QAudioOutput()
        output.setVolume(0)
        player.setAudioOutput(output)
        positions: list[int] = []
        ended: list[bool] = []
        player.positionChanged.connect(positions.append)
        player.mediaStatusChanged.connect(
            lambda status: ended.append(True)
            if status == QMediaPlayer.MediaStatus.EndOfMedia
            else None
        )
        player.setSource(QUrl.fromLocalFile(str(source)))
        player.play()
        self._process_until(lambda: bool(ended), timeout=6.0)
        self.assertGreaterEqual(max(positions, default=0), 3300)
        player.stop()

    def test_page_async_import_enables_preview_without_export(self) -> None:
        source = make_wav(self.root / "import.wav", 600)
        page = AudioProcessingPage()
        page._add_audio_paths([str(source)])
        self.assertIn(page._playback_state, (PlaybackState.PREPARING, PlaybackState.READY))
        self._process_until(lambda: not page._waveform_threads)
        self.assertEqual(page._playback_state, PlaybackState.READY)
        self.assertTrue(page.preview_button.isEnabled())
        self.assertEqual(page._timeline.duration_ms, 600)
        page.request_safe_close()
        page.close()

    def test_rendering_thirty_clips_does_not_probe_or_decode_on_zoom(self) -> None:
        model = TimelineModel()
        for _ in range(30):
            model.add_blank(duration=4.0)
        timeline = PyQtGraphTimeline()
        timeline.resize(1000, 260)
        timeline.show()
        timeline.set_timeline(model)
        self.app.processEvents()
        started = time.perf_counter()
        for pps in (5, 10, 25, 50, 100, 250, 500, 1000):
            timeline.set_pixels_per_second(pps)
            self.app.processEvents()
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 1.0)
        self.assertEqual(len(timeline._clip_items), 30)
        timeline.close()

    def test_audio_control_bar_removes_redo_and_pause_and_adds_split(self) -> None:
        page = AudioProcessingPage()
        expected = [
            "添加音频",
            "插入2秒空白",
            "删除选中",
            "音频裁剪",
            "撤销",
            "试听音轨",
            "停止",
            "循环选中",
        ]
        actual = [
            page.add_audio_button.text(),
            page.blank_button.text(),
            page.remove_button.text(),
            page.split_button.text(),
            page.undo_button.text(),
            page.preview_button.text(),
            page.stop_button.text(),
            page.loop_selected.text(),
        ]
        self.assertEqual(actual, expected)
        self.assertFalse(hasattr(page, "pause_button"))
        self.assertFalse(any(button.text() == "重做" for button in page.findChildren(QAbstractButton)))
        self.assertFalse(page.findChildren(QShortcut))
        page.close()

    def test_clip_click_and_hover_have_separate_permanent_times(self) -> None:
        class Event:
            def __init__(self, local_x: float, scene_x: float = 100.0) -> None:
                self._local = QPointF(local_x, 0.5)
                self._scene = QPointF(scene_x, 100)

            def pos(self) -> QPointF:
                return self._local

            def scenePos(self) -> QPointF:
                return self._scene

            def modifiers(self):
                return Qt.KeyboardModifier.NoModifier

            def accept(self) -> None:
                pass

        model = TimelineModel()
        model.add_blank(duration=1.0)
        audio = model.add_audio(self.root / "source.wav", 3.0)
        model.trim_ms(audio.clip_id, 425, 2425)
        timeline = PyQtGraphTimeline()
        timeline.resize(1000, 250)
        timeline.show()
        timeline.set_timeline(model)
        timeline.set_playhead_ms(250)
        requested: list[int] = []
        hovered: list[object] = []
        timeline.playhead_requested.connect(requested.append)
        timeline.hover_changed.connect(hovered.append)
        item = timeline._clip_items[1]
        item.hoverMoveEvent(Event(500 / 1000))
        timeline._flush_hover()
        self.assertEqual(timeline.playhead_time_ms, 250)
        self.assertTrue(timeline.hover_line.isVisible())
        self.assertTrue(timeline.hover_label.isVisible())
        info = hovered[-1]
        self.assertEqual(info.timeline_ms, 1500)
        self.assertEqual(info.clip_offset_ms, 500)
        self.assertEqual(info.source_ms, 925)
        item.mousePressEvent(Event(750 / 1000))
        item.mouseReleaseEvent(Event(750 / 1000))
        self.assertEqual(requested[-1], 1750)
        item.hoverLeaveEvent(Event(0))
        timeline._flush_hover()
        self.assertIsNone(hovered[-1])
        self.assertFalse(timeline.hover_line.isVisible())
        self.assertFalse(timeline.hover_label.isVisible())
        timeline.close()

    def test_playhead_handle_drag_uses_view_coordinates_after_scroll_and_zoom(self) -> None:
        model = TimelineModel()
        model.add_blank(duration=10.0)
        timeline = PyQtGraphTimeline()
        timeline.resize(1000, 250)
        timeline.show()
        timeline.set_timeline(model)
        timeline.set_pixels_per_second(500)
        timeline.view_box.setXRange(2.0, 3.0, padding=0)
        self.app.processEvents()
        requested: list[int] = []
        timeline.playhead_requested.connect(requested.append)

        class Event:
            def __init__(self, scene: QPointF) -> None:
                self._scene = scene

            def scenePos(self) -> QPointF:
                return self._scene

            def accept(self) -> None:
                pass

        scene = timeline.view_box.mapViewToScene(QPointF(2.345, 0.5))
        event = Event(scene)
        timeline.playhead_handle.mousePressEvent(event)
        timeline.playhead_handle.mouseMoveEvent(event)
        timeline.playhead_handle.mouseReleaseEvent(event)
        self.assertEqual(requested[-1], 2345)
        self.assertEqual(timeline.playhead_time_ms, 2345)
        timeline.set_pixels_per_second(1000)
        self.assertEqual(timeline.playhead_time_ms, 2345)
        timeline.close()

    def test_real_qt_mouse_click_routes_from_clip_to_playhead(self) -> None:
        model = TimelineModel()
        model.add_audio(self.root / "mouse.wav", 4.0)
        timeline = PyQtGraphTimeline()
        timeline.resize(1000, 250)
        timeline.show()
        timeline.set_timeline(model)
        timeline.set_pixels_per_second(200)
        self.app.processEvents()
        requested: list[int] = []
        timeline.playhead_requested.connect(requested.append)
        clip = timeline._clip_items[0]
        scene_point = clip.mapToScene(QPointF(1.5, 0.5))
        viewport_point = timeline.graph.mapFromScene(scene_point)
        timeline.set_playhead_ms(250)
        QTest.mouseMove(timeline.graph.viewport(), viewport_point)
        QTest.qWait(25)
        self.assertEqual(timeline.playhead_time_ms, 250)
        QTest.mouseClick(
            timeline.graph.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_point,
        )
        self.app.processEvents()
        self.assertTrue(requested)
        self.assertLessEqual(abs(requested[-1] - 1500), 1)
        handle_center = timeline.playhead_handle.boundingRect().center()
        handle_start = timeline.graph.mapFromScene(timeline.playhead_handle.mapToScene(handle_center))
        handle_target_scene = timeline.view_box.mapViewToScene(QPointF(2.25, 0.95))
        handle_target = timeline.graph.mapFromScene(handle_target_scene)
        QTest.mousePress(
            timeline.graph.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            handle_start,
        )
        QTest.mouseMove(timeline.graph.viewport(), handle_target, delay=25)
        QTest.mouseRelease(
            timeline.graph.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            handle_target,
        )
        self.app.processEvents()
        self.assertLessEqual(abs(timeline.playhead_time_ms - 2250), 2)
        timeline.close()

    def test_page_split_selects_right_and_undo_restores_original_and_playhead(self) -> None:
        page = AudioProcessingPage()
        source = make_wav(self.root / "split-page.wav", 3386)
        original = page._timeline.add_audio(source, 3.386)
        page._render_timeline()
        page._seek(1250)
        self.assertTrue(page.split_button.isEnabled())
        page._split_audio()
        self.assertEqual(len(page._timeline.items), 2)
        left, right = page._timeline.items
        self.assertEqual((left.trim_start_ms, left.effective_end_ms), (0, 1250))
        self.assertEqual((right.trim_start_ms, right.effective_end_ms), (1250, 3386))
        self.assertEqual(page._selected, {right.clip_id})
        self.assertEqual(page.playhead_time_ms, 1250)
        self.assertEqual(page._timeline.snapshot().total_duration_ms, 3386)
        page._undo()
        self.assertEqual(len(page._timeline.items), 1)
        self.assertEqual(page._timeline.items[0].clip_id, original.clip_id)
        self.assertEqual(page._selected, {original.clip_id})
        self.assertEqual(page.playhead_time_ms, 1250)
        page.close()

    def test_preview_start_uses_playhead_and_respects_loop_range(self) -> None:
        page = AudioProcessingPage()
        first = page._timeline.add_blank(duration=1.0)
        second = page._timeline.add_blank(duration=2.0)
        page._render_timeline()
        page.playhead_time_ms = 1250
        self.assertEqual(page._preview_start_position(3000), 1250)
        page._selected = {second.clip_id}
        page.loop_selected.setChecked(True)
        page.playhead_time_ms = 250
        self.assertEqual(page._preview_start_position(3000), 1000)
        page.playhead_time_ms = 3000
        page.loop_selected.setChecked(False)
        self.assertEqual(page._preview_start_position(3000), 0)
        self.assertEqual(page.playhead_time_ms, 0)
        self.assertNotIn(first.clip_id, page._selected)
        page.close()

    def test_cached_preview_really_starts_from_playhead_and_reaches_end(self) -> None:
        source = make_wav(self.root / "seek-preview.wav", 2000)
        page = AudioProcessingPage()
        page._timeline.add_audio(source, 2.0)
        page._render_timeline()
        page._preview_path = source
        page._preview_version = page._timeline.snapshot().version
        page._seek(750)
        page._preview()
        self._process_until(
            lambda: page._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
            timeout=3.0,
        )
        self.assertGreaterEqual(page._player.position(), 700)
        self._process_until(
            lambda: page._playback_state is PlaybackState.READY
            and page.playhead_time_ms == 2000,
            timeout=4.0,
        )
        self.assertEqual(page.playhead_time_ms, 2000)
        page._preview_path = None
        page._player.stop()
        page.close()

    def test_natural_end_can_restart_five_times_without_manual_stop(self) -> None:
        source = make_wav(self.root / "repeat-preview.wav", 300)
        page = AudioProcessingPage()
        page._timeline.add_audio(source, 0.3)
        page._render_timeline()
        page._preview_path = source
        page._preview_version = page._timeline.snapshot().version
        play_starts = 0

        def count_start(state: QMediaPlayer.PlaybackState) -> None:
            nonlocal play_starts
            if state == QMediaPlayer.PlaybackState.PlayingState:
                play_starts += 1

        page._player.playbackStateChanged.connect(count_start)
        for expected_start in range(1, 6):
            page._preview()
            self._process_until(lambda: play_starts >= expected_start, timeout=2.0)
            self._process_until(
                lambda: page._playback_state is PlaybackState.READY,
                timeout=2.0,
            )
            self.assertEqual(page.playhead_time_ms, 300)
            self.assertTrue(page.preview_button.isEnabled())
            self.assertEqual(page._player.position(), 0)
            self.assertIsNone(page._active_playback_session_id)
        page._preview_path = None
        page._player.stop()
        page.close()

    def test_natural_end_then_middle_seek_and_user_stop_both_restart(self) -> None:
        source = make_wav(self.root / "seek-after-end.wav", 800)
        page = AudioProcessingPage()
        page._timeline.add_audio(source, 0.8)
        page._render_timeline()
        page._preview_path = source
        page._preview_version = page._timeline.snapshot().version
        page._preview()
        self._process_until(lambda: page._playback_state is PlaybackState.READY, timeout=3.0)
        page._seek(400)
        page._preview()
        self._process_until(
            lambda: page._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
            timeout=2.0,
        )
        self.assertGreaterEqual(page._player.position(), 350)
        active_session = page._active_playback_session_id
        # A stale terminal callback from the preceding session must not finalize
        # the new session while it is still near its start.
        page._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
        self.assertEqual(page._active_playback_session_id, active_session)
        self.assertEqual(page._playback_state, PlaybackState.PLAYING)
        page._stop()
        self.assertEqual(page.playhead_time_ms, 0)
        self.assertEqual(page._playback_state, PlaybackState.STOPPED)
        page._preview()
        self._process_until(
            lambda: page._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
            timeout=2.0,
        )
        self.assertLess(page._player.position(), 250)
        self._process_until(lambda: page._playback_state is PlaybackState.READY, timeout=3.0)
        page._preview_path = None
        page._player.stop()
        page.close()

    def test_complex_trim_blank_and_split_preview_restarts(self) -> None:
        first = make_wav(self.root / "repeat-first.wav", 300, 440)
        second = make_wav(self.root / "repeat-second.wav", 300, 660)
        model = TimelineModel()
        first_clip = model.add_audio(first, 0.3)
        model.trim_ms(first_clip.clip_id, 50, 250)
        model.add_blank(duration=0.1)
        second_clip = model.add_audio(second, 0.3)
        model.split_audio_at(second_clip.clip_id, 450)
        snapshot = model.snapshot()
        self.assertEqual(snapshot.total_duration_ms, 600)
        preview = self.root / "complex-repeat.wav"
        results: list[tuple] = []
        worker = AudioPreviewService(snapshot, ExportSettings(), preview, threading.Event())
        worker.finished.connect(lambda *args: results.append(args))
        worker.run()
        self.assertTrue(results[-1][0], results)

        page = AudioProcessingPage()
        page._timeline = model
        page._render_timeline()
        page._preview_path = preview
        page._preview_version = snapshot.version
        starts = 0

        def count_start(state: QMediaPlayer.PlaybackState) -> None:
            nonlocal starts
            if state == QMediaPlayer.PlaybackState.PlayingState:
                starts += 1

        page._player.playbackStateChanged.connect(count_start)
        for expected in (1, 2):
            page._preview()
            self._process_until(lambda: starts >= expected, timeout=2.0)
            self._process_until(lambda: page._playback_state is PlaybackState.READY, timeout=3.0)
            self.assertEqual(page.playhead_time_ms, 600)
        page._preview_path = None
        page._player.stop()
        page.close()

    def test_loop_selected_does_not_finalize_the_whole_timeline(self) -> None:
        source = make_wav(self.root / "loop-preview.wav", 300)
        page = AudioProcessingPage()
        clip = page._timeline.add_audio(source, 0.3)
        page._selected = {clip.clip_id}
        page.loop_selected.setChecked(True)
        page._render_timeline()
        page._preview_path = source
        page._preview_version = page._timeline.snapshot().version
        page._preview()
        self._process_until(
            lambda: page._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
            timeout=2.0,
        )
        QTest.qWait(900)
        self.app.processEvents()
        self.assertEqual(page._playback_state, PlaybackState.PLAYING)
        self.assertIsNotNone(page._active_playback_session_id)
        self.assertLess(page.playhead_time_ms, 300)
        page._stop()
        page._preview_path = None
        page.close()

    def test_split_preview_and_formal_export_consume_the_same_snapshot(self) -> None:
        source = make_wav(self.root / "split-shared.wav", 3386)
        model = TimelineModel()
        clip = model.add_audio(source, 3.386)
        split = model.split_audio_at(clip.clip_id, 1000)
        model.trim_ms(split.right_clip_id, 1500, 3386)
        snapshot = model.snapshot()
        self.assertEqual(snapshot.total_duration_ms, 2886)
        preview = self.root / "split-preview.wav"
        exported = self.root / "split-export.wav"
        preview_results: list[tuple] = []
        export_results: list[tuple] = []
        preview_worker = AudioPreviewService(
            snapshot,
            ExportSettings(),
            preview,
            threading.Event(),
        )
        preview_worker.finished.connect(lambda *args: preview_results.append(args))
        preview_worker.run()
        export_worker = AudioExportService(
            snapshot,
            ExportSettings(),
            exported,
            threading.Event(),
        )
        export_worker.finished.connect(lambda *args: export_results.append(args))
        export_worker.run()
        self.assertTrue(preview_results[-1][0], preview_results)
        self.assertTrue(export_results[-1][0], export_results)
        preview_ms = FfmpegLocator.probe_duration_ms(preview)
        export_ms = FfmpegLocator.probe_duration_ms(exported)
        self.assertLessEqual(abs(preview_ms - 2886), 5)
        self.assertEqual(preview_ms, export_ms)


if __name__ == "__main__":
    unittest.main()
