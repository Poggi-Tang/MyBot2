from PySide6.QtWidgets import QApplication

from .resources import down_arrow_path, left_arrow_path, up_arrow_path


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    stylesheet = (
        """
        * { font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; color: #242629; }
        QMainWindow, QWidget { background: #f7f7f7; }
        QMainWindow { border: 1px solid #dedfe3; }
        QFrame#dockBar {
            background: rgba(246, 246, 246, 246);
            border: 1px solid #d7d8dc;
            border-radius: 8px;
        }
        QFrame#connectionBar, QFrame#statusSummary {
            background: #ffffff;
            border: 1px solid #e2e3e7;
            border-radius: 6px;
        }
        QLabel {
            background: transparent;
            border: 0;
        }
        QLabel#brand { color: #111214; font-size: 20px; font-weight: 600; }
        QLabel#muted { color: #8a8d94; }
        QLabel#pageTitle { color: #161719; font-size: 20px; font-weight: 600; }
        QLabel#sectionTitle { color: #303236; font-size: 14px; font-weight: 600; }
        QLabel#connectionStatus { color: #a7abb3; font-weight: 600; }
        QPushButton {
            background: #ffffff;
            border: 1px solid #d9dade;
            border-radius: 5px;
            padding: 7px 13px;
            color: #303236;
        }
        QPushButton:hover { background: #f2f3f5; border-color: #c4c6cb; }
        QPushButton:pressed { background: #e9eaed; }
        QPushButton:disabled { background: #f4f4f5; color: #b5b7bc; border-color: #e7e8ea; }
        QPushButton#primary { background: #07c160; border-color: #07c160; color: white; font-weight: 600; }
        QPushButton#primary:hover { background: #06ad56; }
        QPushButton#dockButton {
            border: 0;
            border-radius: 5px;
            padding: 6px 10px;
            background: transparent;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton#dockButton:hover { background: #e9eaec; }
        QPushButton#dockButton:checked { background: #dff6e9; color: #07974b; }
        QPushButton#dockAutoChat {
            border: 0;
            border-radius: 5px;
            padding: 6px;
            background: transparent;
        }
        QPushButton#dockAutoChat:hover { background: #e9eaec; }
        QPushButton#dockAutoChat[running="true"] { background: #dff6e9; }
        QPushButton#dockAutoChat:disabled { background: #f0f1f2; }
        QFrame#dockTaskStrip {
            background: #ffffff;
            border: 1px solid #d7d8dc;
            border-radius: 3px;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
        QListWidget, QTableWidget, QDateEdit {
            background: #ffffff;
            border: 1px solid #dfe0e4;
            border-radius: 5px;
            padding: 7px;
            color: #242629;
            selection-background-color: #ccefdc;
            selection-color: #161719;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
        QListWidget:focus, QTableWidget:focus { border-color: #07c160; }
        QComboBox { padding-right: 32px; }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            border: 0;
        }
        QComboBox::down-arrow {
            image: url("__LEFT_ARROW__");
            width: 16px;
            height: 16px;
        }
        QComboBox::down-arrow:on { image: url("__DOWN_ARROW__"); }
        QSpinBox, QDoubleSpinBox { padding-right: 30px; }
        QSpinBox::up-button, QDoubleSpinBox::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 26px;
            height: 50%;
            background: transparent;
            border: 0;
            border-left: 1px solid #e3e4e7;
            border-bottom: 1px solid #eeeeef;
            border-top-right-radius: 5px;
        }
        QSpinBox::down-button, QDoubleSpinBox::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 26px;
            height: 50%;
            background: transparent;
            border: 0;
            border-left: 1px solid #e3e4e7;
            border-bottom-right-radius: 5px;
        }
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
            background: #f0f1f3;
        }
        QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
        QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
            background: #e4e6e9;
        }
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
            image: url("__DOWN_ARROW__");
            width: 12px;
            height: 12px;
        }
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
            image: url("__UP_ARROW__");
            width: 12px;
            height: 12px;
        }
        QListWidget { outline: none; }
        QListWidget::item { padding: 8px 7px; border-bottom: 1px solid #eeeeef; }
        QListWidget::item:selected { background: #dff6e9; color: #18191b; }
        QTableWidget { gridline-color: #e9eaec; alternate-background-color: #fafafa; }
        QHeaderView::section {
            background: #f3f4f5;
            color: #696c72;
            border: 0;
            border-right: 1px solid #e3e4e7;
            border-bottom: 1px solid #dfe0e4;
            padding: 8px;
        }
        QScrollBar:vertical { background: transparent; width: 9px; margin: 1px; }
        QScrollBar::handle:vertical { background: #c7c9ce; border-radius: 4px; min-height: 24px; }
        QProgressBar { background: #e9eaec; border: 0; border-radius: 3px; text-align: center; color: #55585e; }
        QProgressBar::chunk { background: #07c160; border-radius: 3px; }
        QTabWidget::pane { border: 1px solid #e0e1e4; background: #ffffff; }
        QTabBar::tab { background: #f4f4f5; color: #74777d; padding: 9px 15px; border: 0; }
        QTabBar::tab:selected { background: #ffffff; color: #07974b; border-bottom: 2px solid #07c160; }
        QToolTip { background: #3c3f43; color: #ffffff; border: 0; padding: 5px; }
        """
    )
    stylesheet = stylesheet.replace(
        "__LEFT_ARROW__", left_arrow_path().as_posix()
    ).replace("__DOWN_ARROW__", down_arrow_path().as_posix()).replace(
        "__UP_ARROW__", up_arrow_path().as_posix()
    )
    app.setStyleSheet(stylesheet)
