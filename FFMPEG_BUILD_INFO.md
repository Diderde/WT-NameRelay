# FFmpeg binary provenance and source information

WT-NameRelay currently bundles the Windows x64 shared-library build reported by
the binary as:

```text
ffmpeg version N-125829-gfe953596e9-20260728
built with gcc 15.2.0 (crosstool-NG 1.28.0.23_185f348)
license: LGPL-3.0-or-later
```

The build was obtained from the BtbN FFmpeg-Builds `win64-lgpl-shared`
distribution. Its embedded configuration includes `--enable-version3`,
`--enable-shared`, `--disable-static`, does not include `--enable-gpl` or
`--enable-nonfree`, and disables GPL-only x264/x265/xvid/vidstab/rubberband
components used in other variants.

- FFmpeg upstream source: https://github.com/FFmpeg/FFmpeg
- Referenced upstream revision: https://github.com/FFmpeg/FFmpeg/commit/fe953596e9
- BtbN build scripts and source links: https://github.com/BtbN/FFmpeg-Builds
- FFmpeg legal and source-distribution checklist: https://ffmpeg.org/legal.html

The exact embedded configure line can be inspected without executing the main
application:

```powershell
.\app\resources\ffmpeg\bin\ffmpeg.exe -version
.\app\resources\ffmpeg\bin\ffmpeg.exe -L
```

Before publishing a binary GitHub Release, the release maintainer must attach
or host the corresponding FFmpeg source bundle and build information alongside
the application download, and link that source from the Release notes. Merely
linking to the moving upstream default branch is not sufficient evidence of
corresponding source.

This file records technical provenance and is not legal advice.
