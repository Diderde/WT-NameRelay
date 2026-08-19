# Timeline Component Evaluation

## Current implementation

The previous timeline is one custom `QWidget` wrapped in a `QScrollArea`. It creates
no per-tick `QLabel` or child widgets. Ruler labels, clip rectangles, placeholder
waveforms and the playhead are all painted in `paintEvent()`.

## Root causes

- **Overlapping ruler text:** tick spacing was chosen from a small fixed threshold
  table and labels were drawn without measuring their text rectangles.
- **Slow zoom and scrolling:** zoom changed the canvas minimum width and every paint
  traversed every clip and all calculated ticks. Waveform data had one resolution
  only and was resampled repeatedly while painting.
- **Trim looked ineffective:** drag preview emitted values but did not update a
  preview model. Only mouse release committed to `TimelineModel`, and playback and
  export accepted mutable item tuples independently instead of one frozen snapshot.
- **Incomplete preview playback:** preview generation had no explicit snapshot
  duration contract or post-render duration assertion. Loop/end handling could stop
  from UI-derived ranges rather than the rendered cache duration.

## Component evaluation

| Candidate | License | Native PySide6 | Multi-clip / trim | Runtime impact | Decision |
| --- | --- | --- | --- | --- | --- |
| PyQtGraph 0.13.7 | MIT | Yes | Custom `GraphicsObject` | NumPy + ~2 MB Python package | Selected |
| waveform-playlist | MIT | Via QtWebEngine/QWebChannel | Built in | QtWebEngine + JS toolchain, about 150 MB in this environment | Fallback only |
| wavesurfer.js | BSD-3-Clause | Via QtWebEngine/QWebChannel | Regions, not final rendering | Same WebEngine bridge and packaging risk | Not selected |

PyQtGraph remains a view and interaction layer. The Python timeline model,
`TimelineSnapshot`, FFmpeg export and project completion logic remain authoritative.

Official sources reviewed:

- PyQtGraph repository and license: https://github.com/pyqtgraph/pyqtgraph
- PyQtGraph plotting performance options: https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/plotdataitem.html
- waveform-playlist repository and license: https://github.com/naomiaro/waveform-playlist
- wavesurfer.js repository and license: https://github.com/katspaugh/wavesurfer.js

PyQtGraph remains actively maintained; 0.13.7 is intentionally pinned for the
project's Python 3.11 / PySide6 6.7.3 environment instead of changing the Qt stack.
The Web candidates both need QtWebEngine and a Python/JavaScript state bridge.
Neither is required after the PyQtGraph prototype passed.

## Prototype gate

`tools/timeline_pyqtgraph_prototype.py --verify` uses a generated four-second WAV
and passed all integration gates:

- real cached waveform available;
- trim changed the authoritative range to 425–3120 ms;
- the same snapshot rendered a 2695 ms preview (verified by ffprobe);
- the ruler selected seconds at the initial view;
- zoom retained time zero at the left edge.
