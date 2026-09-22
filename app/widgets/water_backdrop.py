# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""全窗口水纹流动背板（玻璃卡片视觉的全局底衬）。

渲染路径：GLSL 域扭曲 fBm 着色器（与视觉稿 temp/mockup_glass.html 同源）在
离屏 GL 上下文中渲染成 QImage，由普通 QWidget 以 QPainter 显示。
刻意不让 QOpenGLWidget 进入控件树——GL 控件与兄弟控件的屏幕级合成在部分
驱动/平台上不可靠（表现为上层 UI 被水纹覆盖），QImage 显示路径则无此问题。
GL 初始化失败时退回 QPainter 缓动光斑（1/3 分辨率）。
偏好 ``ui/motion`` = "reduced" 时只渲染静态单帧（晕动症与低配机的关闭开关）。
"""

from __future__ import annotations

import contextlib
import math
import struct
import time
from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QOffscreenSurface,
    QOpenGLContext,
    QPainter,
    QRadialGradient,
    QSurfaceFormat,
)
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLShader,
    QOpenGLShaderProgram,
)
from PySide6.QtWidgets import QWidget

from app.preferences import get_preference, set_preference
from app.styles import theme

MOTION_KEY = "ui/motion"
MOTION_FULL = "full"
MOTION_REDUCED = "reduced"

_MOTION_LISTENERS: list[Callable[[bool], None]] = []

# GL 常量（避免依赖外部 GL 绑定）：GL_FLOAT / GL_TRIANGLES
_GL_FLOAT = 0x1406
_GL_TRIANGLES = 0x0004

_VERTEX_SHADER = "attribute vec2 a;void main(){gl_Position=vec4(a,0.0,1.0);}"

_FRAGMENT_SHADER = """uniform vec2 u_res;uniform float u_time;
uniform vec3 u_c0;uniform vec3 u_c1;uniform vec3 u_c2;uniform vec3 u_hi;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);vec2 u=f*f*(3.0-2.0*f);
 float a=hash(i),b=hash(i+vec2(1.0,0.0)),c=hash(i+vec2(0.0,1.0)),d=hash(i+vec2(1.0,1.0));
 return mix(mix(a,b,u.x),mix(c,d,u.x),u.y);}
float fbm(vec2 p){float v=0.0,a=0.5;mat2 r=mat2(0.80,0.60,-0.60,0.80);
 for(int i=0;i<5;i++){v+=a*noise(p);p=r*p*2.03;a*=0.5;}return v;}
void main(){
 vec2 uv=gl_FragCoord.xy/u_res.xy;
 vec2 p=(gl_FragCoord.xy-0.5*u_res.xy)/min(u_res.x,u_res.y);
 float t=u_time*0.26;
 vec2 d1=vec2(0.170,-0.120), d2=vec2(-0.145,0.105);
 float q1=fbm(p*1.55+d1*t+3.1);
 float q2=fbm(p*1.55+d2*t-1.7);
 float f=fbm(p*1.25+vec2(q1,q2)*1.15-d1*t*1.6);
 float g=fbm(p*2.55-vec2(q2,q1)*0.75+vec2(t*0.9,t*0.55));
 vec3 col=mix(u_c0,u_c2,smoothstep(0.10,0.90,f));
 col=mix(col,u_c1,smoothstep(0.45,1.00,g)*0.42);
 float s=fbm(p*3.30+vec2(t*1.55,-t*1.15));
 float band=fbm(p*0.62+vec2(t*0.62,-t*0.44));
 float vein=pow(clamp(1.0-abs(f-0.55)*3.1,0.0,1.0),3.0);
 vein+=0.35*pow(s,3.0);
 col+=u_hi*vein*0.26;
 col*=0.84+0.32*smoothstep(0.25,0.85,band);
 col*=mix(0.92,1.06,smoothstep(1.0,0.0,uv.y));
 float vig=smoothstep(1.30,0.32,length(uv-0.5));
 col*=mix(0.87,1.0,vig);
 gl_FragColor=vec4(col,1.0);}"""


def is_reduced_motion() -> bool:
    return str(get_preference(MOTION_KEY, MOTION_FULL)).lower() == MOTION_REDUCED


def set_reduced_motion(reduced: bool) -> None:
    set_preference(MOTION_KEY, MOTION_REDUCED if reduced else MOTION_FULL)
    for listener in _MOTION_LISTENERS:
        listener(reduced)


def on_motion_changed(listener: Callable[[bool], None]) -> None:
    _MOTION_LISTENERS.append(listener)


def _rgb(key: str) -> tuple[float, float, float]:
    color = QColor(theme.PALETTES[theme.current_mode()][key])
    return (color.redF(), color.greenF(), color.blueF())


def _mix(a: tuple[float, float, float], b: tuple[float, float, float], k: float) -> tuple[float, float, float]:
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k)


def _water_palette() -> dict[str, tuple[float, float, float]]:
    """以底色为水，混入金色/蓝/青三色，得到着色器四路颜色。"""
    base = _rgb("background")
    return {
        "c0": _mix(base, _rgb("water_deep"), 0.60),
        "c1": _mix(base, _rgb("water_gold"), 0.52),
        "c2": _mix(base, _rgb("water_blue"), 0.60),
        "hi": _mix(base, _rgb("water_teal"), 0.45),
    }


class _WaterRenderer:
    """离屏 GL 渲染器：着色器水纹 → QImage。任何 GL 故障收敛为 ensure() 返回 False。"""

    def __init__(self) -> None:
        self._surface: QOffscreenSurface | None = None
        self._context: QOpenGLContext | None = None
        self._program: QOpenGLShaderProgram | None = None
        self._buffer: QOpenGLBuffer | None = None
        self._fbo: QOpenGLFramebufferObject | None = None
        self._fbo_size = (0, 0)
        self._ok = False

    def is_ok(self) -> bool:
        return self._ok

    def _setup(self) -> None:
        if self._ok:
            return
        format_ = QSurfaceFormat()
        format_.setAlphaBufferSize(8)
        self._surface = QOffscreenSurface()
        self._surface.setFormat(format_)
        self._surface.create()
        context = QOpenGLContext()
        context.setFormat(format_)
        if not context.create():
            raise RuntimeError("QOpenGLContext.create() failed")
        if not context.makeCurrent(self._surface):
            raise RuntimeError("makeCurrent on offscreen surface failed")
        self._context = context
        program = QOpenGLShaderProgram()
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX_SHADER):
            raise RuntimeError(program.log())
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT_SHADER):
            raise RuntimeError(program.log())
        if not program.link():
            raise RuntimeError(program.log())
        program.bind()
        buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        buffer.create()
        buffer.bind()
        buffer.allocate(struct.pack("<6f", -1.0, -1.0, 3.0, -1.0, -1.0, 3.0), 6 * 4)
        buffer.release()
        self._program = program
        self._buffer = buffer
        self._ok = True

    def render(self, width: int, height: int, time_value: float) -> QImage | None:
        """渲染一帧水纹（width×height 像素），失败返回 None。"""
        try:
            self._setup()
            assert self._context is not None and self._program is not None and self._buffer is not None
            if self._fbo is None or self._fbo_size != (width, height):
                self._fbo = QOpenGLFramebufferObject(width, height)
                self._fbo_size = (width, height)
            self._context.makeCurrent(self._surface)
            palette = _water_palette()
            self._fbo.bind()
            self._context.functions().glViewport(0, 0, width, height)
            self._program.bind()
            self._buffer.bind()
            self._program.enableAttributeArray(self._program.attributeLocation("a"))
            self._program.setAttributeBuffer(
                self._program.attributeLocation("a"), _GL_FLOAT, 0, 2, 0
            )
            self._context.functions().glUniform2f(
                self._program.uniformLocation("u_res"), float(width), float(height)
            )
            self._context.functions().glUniform1f(self._program.uniformLocation("u_time"), time_value)
            self._context.functions().glUniform3f(self._program.uniformLocation("u_c0"), *palette["c0"])
            self._context.functions().glUniform3f(self._program.uniformLocation("u_c1"), *palette["c1"])
            self._context.functions().glUniform3f(self._program.uniformLocation("u_c2"), *palette["c2"])
            self._context.functions().glUniform3f(self._program.uniformLocation("u_hi"), *palette["hi"])
            self._context.functions().glDrawArrays(_GL_TRIANGLES, 0, 3)
            self._program.disableAttributeArray(self._program.attributeLocation("a"))
            self._buffer.release()
            self._program.release()
            image = self._fbo.toImage()
            self._fbo.release()
            self._context.doneCurrent()
            return image if not image.isNull() else None
        except Exception:  # noqa: BLE001 — GL 环境千差万别，一律走降级
            self._ok = False
            self._context_done_current_safe()
            return None

    def _context_done_current_safe(self) -> None:
        with contextlib.suppress(Exception):
            if self._context is not None:
                self._context.doneCurrent()


class WaterBackdrop(QWidget):
    """宿主控件：显示离屏渲染的水纹帧，GL 不可用时自绘缓动光斑。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("waterBackdrop")
        self._renderer = _WaterRenderer()
        self._use_painter = False
        self._time = 12.0
        self._last_tick: float | None = None
        self._frame: QImage | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        theme.on_mode_changed(self._on_mode_changed)
        on_motion_changed(self._on_motion_changed)

    # ── 生命周期 ──
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_motion()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        self._frame = None
        super().resizeEvent(event)

    def _on_mode_changed(self, _mode: str) -> None:
        self._frame = None
        if self.isVisible():
            self._apply_motion()

    def _on_motion_changed(self, _reduced: bool) -> None:
        if self.isVisible():
            self._apply_motion()

    # ── 动效状态 ──
    def _apply_motion(self) -> None:
        if is_reduced_motion():
            self._timer.stop()
            self._time = 12.0
            self._render_frame()
            self.update()
            return
        self._last_tick = None
        self._timer.start()

    def _tick(self) -> None:
        if self.window().isMinimized():
            return
        now = time.monotonic()
        if self._last_tick is None:
            self._last_tick = now
            return
        self._time = (self._time + (now - self._last_tick) * 1.30) % 4096.0
        self._last_tick = now
        self._render_frame()
        self.update()

    def _render_frame(self) -> None:
        width = max(2, self.width() // 2)
        height = max(2, self.height() // 2)
        if not self._use_painter:
            frame = self._renderer.render(width, height, self._time)
            if frame is not None:
                self._frame = frame
                return
            self._use_painter = True
            self._frame = None
        self._render_painter_frame()

    # ── QPainter 降级：缓动光斑 ──
    def _render_painter_frame(self) -> None:
        width = max(2, self.width() // 3)
        height = max(2, self.height() // 3)
        frame = QImage(width, height, QImage.Format.Format_RGB32)
        painter = QPainter(frame)
        background = QColor(theme.PALETTES[theme.current_mode()]["background"])
        painter.fillRect(frame.rect(), background)
        base = self._time
        orbs = (
            (0.16, 0.20, 0.52, "water_gold", 0.50),
            (0.86, 0.34, 0.60, "water_blue", 0.46),
            (0.44, 0.88, 0.50, "water_teal", 0.40),
        )
        for index, (bx, by, radius, key, alpha) in enumerate(orbs):
            cx = (bx + 0.07 * math.sin(base * 0.10 + index)) * width
            cy = (by + 0.06 * math.cos(base * 0.08 + index * 1.7)) * height
            color = QColor(theme.PALETTES[theme.current_mode()][key])
            gradient = QRadialGradient(cx, cy, radius * min(width, height))
            gradient.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), int(255 * alpha)))
            gradient.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.fillRect(frame.rect(), gradient)
        painter.end()
        self._frame = frame

    def paintEvent(self, event) -> None:
        if self._frame is None:
            self._render_frame()
        if self._frame is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self._frame)
        painter.end()
