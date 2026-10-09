from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.branding import APP_NAME, FORK_VERSION, WINDOW_TITLE
from app.logging_setup import configure_logging, install_exception_hooks
from app.main_window import MainWindow
from app.styles.theme import apply_theme
from app.widgets.disclaimer_dialog import DisclaimerDialog

# WebEngine 相关必须在首个 QApplication 之前就位：
# - 共享 OpenGL 上下文（QtWebEngine 的官方要求，缺了会有告警且部分驱动下渲染异常）；
# - --no-sandbox：Chromium 沙箱引导在 Windows 上靠向 QtWebEngineProcess 注入远程线程
#   （CreateRemoteThread），360 等安全软件必报"远程线程注入"。内嵌区只加载本机
#   TTS-Hub 管理台（可信内容），放弃沙箱换取零告警（用户实测点名的
#   唯一告警源；若未来要加载不可信内容需重新评估）；
# - RendererCodeIntegrity 关闭：Windows 代码完整性会拦渲染进程 DLL，与安全软件注入
#   共存时导致渲染崩溃（本地可信内容的常见兼容性问题）。
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-features=RendererCodeIntegrity",
)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)


def main() -> int:
    """Show the mandatory notice before constructing the main window."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)
    logger = configure_logging(); install_exception_hooks(logger)
    logger.info("Application startup (%s)", FORK_VERSION)
    apply_theme(app)
    notice = DisclaimerDialog()
    if notice.exec() != DisclaimerDialog.DialogCode.Accepted:
        logger.info("Disclaimer declined; application closed before main window creation")
        return 0

    try:
        window = MainWindow(); window.showMaximized(); window.activateWindow()
        # 启动期对象（含易碎的原生枚举包装）移出 GC 回收集：昼夜切换的
        # 全局重打磨会在任意分配点触发回收周期，实测在回收半初始化的
        # 枚举包装时原生崩溃；freeze 后该回收链不再参与，崩溃根除
        import gc
        collected = gc.collect()
        gc.freeze()
        logger.info("Startup GC: collected=%d frozen=%d", collected, gc.get_freeze_count())
        # 自动 GC 可由任意线程的分配触发，而视频页运行期
        # 产生的 Qt 包装垃圾被任何 GC 扫描都会段错误（实测：工作线程 GC 崩、
        # GUI 线程定时 GC 同样崩——与回收线程无关，垃圾本身有毒）——
        # 禁用自动回收，只在"视频页退场且工作线程全部安静"的安全点回收
        gc.disable()

        def _safe_collect() -> None:
            page = window.video_clip_page
            if page.isVisible() or page.has_active_workers():
                return
            gc.collect()

        collector = QTimer(app)
        collector.setInterval(10_000)
        collector.timeout.connect(_safe_collect)
        collector.start()
        logger.info("Main window displayed (maximized)")
        exit_code = app.exec()
        logger.info("Application exited with code %s", exit_code)
        return exit_code
    except Exception:
        logger.exception("Startup failed")
        QMessageBox.critical(None, WINDOW_TITLE, "程序启动失败。请查看本地日志获取详细信息。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
