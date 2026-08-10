from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(
        """
        * { font-family: "Microsoft YaHei UI", "Segoe UI"; }
        QMainWindow, QWidget { background: #10151d; color: #e7edf5; }
        QFrame#sidebar { background: #0c1118; border-right: 1px solid #202b38; }
        QFrame#topbar { background: #141b25; border-bottom: 1px solid #202b38; }
        QLabel#brand { color: #f3f7fb; font-size: 22px; font-weight: 700; }
        QLabel#muted { color: #8b9aac; }
        QLabel#pageTitle { color: #f3f7fb; font-size: 24px; font-weight: 700; }
        QLabel#sectionTitle { color: #dbe6f2; font-size: 15px; font-weight: 700; }
        QPushButton { background: #1a2634; border: 1px solid #2a3a4c; border-radius: 6px; padding: 8px 14px; color: #dfe9f4; }
        QPushButton:hover { background: #243548; border-color: #3a91ff; }
        QPushButton:pressed { background: #142331; }
        QPushButton#primary { background: #2d83f7; border-color: #2d83f7; color: white; font-weight: 700; }
        QPushButton#primary:hover { background: #4b98fb; }
        QPushButton#nav { text-align: left; padding: 11px 16px; border: 0; border-radius: 7px; background: transparent; color: #91a1b4; }
        QPushButton#nav:hover { background: #182533; color: #eef5fd; }
        QPushButton#nav:checked { background: #1d3d61; color: #67adff; }
        QPushButton#iconButton { padding: 6px 10px; }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget, QDateEdit {
            background: #141d28; border: 1px solid #2a3a4c; border-radius: 6px; padding: 7px; color: #e7edf5; selection-background-color: #2d83f7;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QListWidget:focus { border-color: #3a91ff; }
        QListWidget { outline: none; }
        QListWidget::item { padding: 9px 8px; border-bottom: 1px solid #1d2834; }
        QListWidget::item:selected { background: #1d3d61; color: #fff; }
        QTableWidget { gridline-color: #253241; alternate-background-color: #131c26; }
        QHeaderView::section { background: #1a2634; color: #aebdcd; border: 0; padding: 8px; }
        QScrollBar:vertical { background: #10151d; width: 10px; margin: 0; }
        QScrollBar::handle:vertical { background: #314255; border-radius: 5px; min-height: 24px; }
        QProgressBar { background: #1a2634; border: 0; border-radius: 4px; text-align: center; color: #eef5fd; }
        QProgressBar::chunk { background: #2d83f7; border-radius: 4px; }
        QTabWidget::pane { border: 1px solid #253241; border-radius: 6px; }
        QTabBar::tab { background: #141d28; color: #8b9aac; padding: 8px 14px; }
        QTabBar::tab:selected { color: #69b0ff; border-bottom: 2px solid #2d83f7; }
        QToolTip { background: #1b2a3b; color: #f5f8fc; border: 1px solid #38516c; padding: 5px; }
        """
    )
