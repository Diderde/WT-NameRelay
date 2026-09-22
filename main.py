from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.branding import APP_NAME, FORK_VERSION, WINDOW_TITLE
from app.logging_setup import configure_logging, install_exception_hooks
from app.main_window import MainWindow
from app.styles.theme import apply_theme
from app.widgets.disclaimer_dialog import DisclaimerDialog


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
        window = MainWindow(); window.showMaximized(); window.activateWindow(); logger.info("Main window displayed (maximized)")
        exit_code = app.exec()
        logger.info("Application exited with code %s", exit_code)
        return exit_code
    except Exception:
        logger.exception("Startup failed")
        QMessageBox.critical(None, WINDOW_TITLE, "程序启动失败。请查看本地日志获取详细信息。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
