import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from takesync.ui import MainWindow
from takesync.models import Anchor, Media, Project
from takesync.planner import regroup


def test_tolerance_control_replans_and_invalidates_preview():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    media = Media('/test.mov', 60, '25', 1920, 1080, 2)
    project = Project(media, media, Media('/master.wav', 10, channels=2), '25', 0, 1,
                      [Anchor(50, 150, .9), Anchor(100, 199, .9), Anchor(150, 248, .9)])
    regroup(project, 0); window.accept_project(project)
    assert len(window.project.sections) == 3
    window.preview_path = '/old-preview.mp4'
    window.tolerance.setValue(2)
    assert len(window.project.sections) == 1
    assert window.preview_path is None
    assert window.export_button.isEnabled()
    assert window.table.rowCount() == 3
    window.close()
