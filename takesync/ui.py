from __future__ import annotations

import argparse
import os
from pathlib import Path
from threading import Event
import sys
import traceback

if sys.platform == 'darwin':
    os.environ.setdefault('QT_MEDIA_BACKEND', 'darwin')

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QStandardPaths, QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPainterPath, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox,
    QStackedWidget, QSlider, QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QAbstractSpinBox, QSplitter, QSizePolicy, QScrollArea)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from .models import Project
from .planner import regroup

STYLE = """
QWidget { color: #e8edf6; font-size: 13px; }
QMainWindow, QWidget#root { background: #0c111b; }
QFrame#sidebar { background: #111925; border-right: 1px solid #253044; }
QFrame#fileCard, QFrame#panel { background: #151f2e; border: 1px solid #29364b; border-radius: 12px; }
QFrame#fileCard[ready="true"] { border-color: #477b6a; background: #152721; }
QLabel { background: transparent; }
QLabel#muted { color: #91a0b7; }
QLabel#eyebrow { color: #89a3c8; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 23px; font-weight: 650; }
QLabel#metric { font-size: 22px; font-weight: 650; color: #a4f5c7; }
QLabel#badge { background: #20372e; color: #a4f5c7; border-radius: 7px; padding: 5px 10px; font-size: 11px; }
QPushButton { background: #202c40; border: 1px solid #35445c; border-radius: 8px; padding: 9px 14px; font-weight: 550; }
QPushButton:hover { background: #2a3b55; border-color: #577093; }
QPushButton:pressed { background: #152135; }
QPushButton:disabled { color: #63718a; background: #172131; border-color: #263247; }
QPushButton#primary { background: #a0f0c2; border-color: #a0f0c2; color: #10261b; font-weight: 700; padding: 13px; }
QPushButton#primary:hover { background: #c0ffda; }
QPushButton#primary:disabled { background: #304c41; color: #809c8c; border-color: #304c41; }
QPushButton#small { padding: 5px 9px; font-size: 11px; }
QSpinBox, QDoubleSpinBox, QComboBox { background: #0f1724; border: 1px solid #34445e; border-radius: 7px; padding: 8px; min-height: 19px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #1b293d; selection-background-color: #365675; }
QGroupBox { border: 1px solid #29364b; border-radius: 9px; margin-top: 9px; padding-top: 12px; color: #aebed4; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTableWidget { background: #111a29; alternate-background-color: #152033; border: none; gridline-color: #253147; selection-background-color: #2b4565; }
QHeaderView::section { background: #1b283b; color: #99aac4; border: none; padding: 8px; font-size: 11px; }
QTableWidget::item { padding: 6px; border-bottom: 1px solid #1f2a3b; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #111a29; width: 8px; }
QScrollBar::handle:vertical { background: #3a4d69; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: #1b293c; border: none; border-radius: 3px; max-height: 5px; min-height: 5px; }
QProgressBar::chunk { background: #a0f0c2; border-radius: 3px; }
QSlider::groove:horizontal { background: #2b3b54; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #a0f0c2; border-radius: 2px; }
QSlider::handle:horizontal { background: #d8ffe8; width: 12px; margin: -5px 0; border-radius: 6px; }
QToolTip { background: #22334c; color: #eef3ff; border: 1px solid #49607f; padding: 7px; }
"""


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def time_text(ms):
    ms = max(0, int(ms))
    return f'{ms//60000:02d}:{ms//1000%60:02d}.{ms%1000:03d}'


class Mark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#263e36'))
        painter.drawRoundedRect(0, 0, 40, 40, 11, 11)
        painter.setPen(QPen(QColor('#a0f0c2'), 2.4, Qt.SolidLine, Qt.RoundCap))
        for x, height in [(9, 8), (15, 20), (21, 13), (27, 25), (33, 6)]:
            painter.drawLine(x-1, int(20-height/2), x-1, int(20+height/2))


class FileCard(QFrame):
    changed = Signal(str)

    def __init__(self, role, title, subtitle):
        super().__init__()
        self.path = ''
        self.title = title
        self.setObjectName('fileCard')
        self.setAcceptDrops(True)
        self.setMinimumHeight(109)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        row = QHBoxLayout()
        row.addWidget(label(role, 'badge'))
        row.addWidget(label(title))
        row.addStretch()
        self.clear_button = QPushButton('×')
        self.clear_button.setObjectName('small')
        self.clear_button.setFixedSize(25, 25)
        self.clear_button.setToolTip('Remove this file')
        self.clear_button.clicked.connect(lambda: self.set_path(''))
        row.addWidget(self.clear_button)
        layout.addLayout(row)
        self.filename = label(subtitle, 'muted', True)
        self.filename.setMinimumHeight(28)
        self.filename.setMaximumHeight(40)
        layout.addWidget(self.filename)
        choose = QPushButton('Choose file…')
        choose.setObjectName('small')
        choose.clicked.connect(self.choose)
        layout.addWidget(choose, alignment=Qt.AlignLeft)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, f'Choose {self.title}', '',
            'Media (*.mov *.mp4 *.mxf *.mkv *.avi *.m4v *.wav *.aif *.aiff *.flac *.mp3 *.m4a);;All files (*)')
        if path:
            self.set_path(path)

    def set_path(self, path):
        self.path = path
        self.filename.setText(Path(path).name if path else 'Drop a file here, or choose one')
        self.filename.setToolTip(path)
        self.setProperty('ready', bool(path))
        self.style().unpolish(self)
        self.style().polish(self)
        self.changed.emit(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.set_path(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()


class EmptyPreview(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor('#0b121d'))
        middle = self.height()//2 - 35
        import math
        for row, colour, phase in [(0, '#426f8c', 0), (45, '#a0f0c2', .6)]:
            pen = QPen(QColor(colour), 2)
            p.setPen(pen)
            path = QPainterPath()
            for x in range(60, max(61, self.width()-60), 3):
                envelope = max(0, math.sin((x-60)/max(self.width()-120, 1)*math.pi))
                y = middle+row+math.sin(x*.085+phase)*16*envelope
                path.moveTo(x, y) if x == 60 else path.lineTo(x, y)
            p.drawPath(path)
        p.setPen(QColor('#e9f2ff'))
        font = p.font(); font.setPixelSize(19); font.setWeight(QFont.DemiBold); p.setFont(font)
        p.drawText(0, middle+82, self.width(), 28, Qt.AlignCenter, 'Two performances. One shared timeline.')
        font.setPixelSize(12); font.setWeight(QFont.Normal); p.setFont(font)
        p.setPen(QColor('#879bb8'))
        p.drawText(0, middle+117, self.width(), 25, Qt.AlignCenter, 'Add your recordings, align the music, then build a preview.')


class VideoCanvas(QWidget):
    """Draw decoded preview frames without a platform-specific video surface."""
    def __init__(self):
        super().__init__()
        self.image = None
        self.frames_received = 0

    def receive_frame(self, frame):
        image = frame.toImage()
        if not image.isNull():
            self.image = image
            self.frames_received += 1
            self.update()

    def clear(self):
        self.image = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#080d15'))
        if self.image is not None:
            fitted = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            target = QRectF((self.width()-fitted.width())/2, (self.height()-fitted.height())/2,
                            fitted.width(), fitted.height())
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawImage(target, self.image)


class Timeline(QWidget):
    seek = Signal(int)

    def __init__(self):
        super().__init__()
        self.project = None
        self.position = 0
        self.setMinimumHeight(128)
        self.setMouseTracking(True)
        self.setToolTip('Click to seek. Yellow lines identify anchors to review.')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        left, width = 32, max(1, self.width()-44)
        duration = self.project.master.duration if self.project else 180
        for index, title in enumerate(['A', 'B', 'M']):
            y = 25+index*29
            p.setPen(QColor('#8da2c1')); p.drawText(3, y+16, title)
            p.setPen(Qt.NoPen); p.setBrush(QColor('#1b2a3e')); p.drawRoundedRect(left, y, width, 22, 4, 4)
            if self.project:
                if title == 'M':
                    p.setBrush(QColor('#426f58')); p.drawRoundedRect(left, y, width, 22, 4, 4)
                else:
                    for section in self.project.sections:
                        a = left+section.start/self.project.frames*width
                        b = left+section.end/self.project.frames*width
                        p.setBrush(QColor('#427f88' if title == 'A' else '#4967a0'))
                        p.drawRoundedRect(a, y, max(1, b-a-1), 22, 3, 3)
        for i in range(5):
            p.setPen(QColor('#7185a2'))
            x = min(self.width()-43, int(left+width*i/4)-1)
            p.drawText(x, 15, time_text(duration*1000*i/4)[:5])
        if self.project:
            for anchor in self.project.anchors:
                if anchor.review:
                    x = int(left+anchor.master_frame/self.project.frames*width)
                    p.setPen(QPen(QColor('#e5bd72'), 1)); p.drawLine(x, 23, x, 78)
        x = int(left+min(1, self.position/max(duration*1000, 1))*width)
        p.setPen(QPen(QColor('#edfff4'), 1.5)); p.drawLine(x, 20, x, 110)

    def mousePressEvent(self, event):
        if self.project:
            ratio = min(1, max(0, (event.position().x()-32)/max(1, self.width()-44)))
            self.seek.emit(int(ratio*self.project.master.duration*1000))


class Worker(QThread):
    progress = Signal(float, str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, task):
        super().__init__()
        self.task = task
        self.cancel_event = Event()

    def run(self):
        try:
            value = self.task(self.progress.emit, self.cancel_event)
            self.result.emit(value)
        except Exception as exc:
            from .media import Cancelled
            if not isinstance(exc, Cancelled):
                traceback.print_exc()
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('TakeSync · local performance alignment')
        self.resize(1380, 930)
        self.setMinimumSize(1100, 800)
        self.project = None
        self.worker = None
        self.preview_path = None
        self.loading = False
        self.close_pending = False
        self.cache = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation))
        self.cache.mkdir(parents=True, exist_ok=True)
        root = QWidget(); root.setObjectName('root'); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(310)
        side = QVBoxLayout(sidebar); side.setContentsMargins(20, 24, 20, 20); side.setSpacing(13)
        brand = QHBoxLayout(); brand.addWidget(Mark()); brand.addWidget(label('TakeSync', 'title')); brand.addStretch()
        side.addLayout(brand); side.addWidget(label('MUSIC, BACK IN TIME', 'eyebrow')); side.addSpacing(8)
        self.cards = [FileCard('A', 'Camera A', 'The main video recording'),
                      FileCard('B', 'Camera B', 'The same take, another angle'),
                      FileCard('M', 'Master audio', 'The final performance to match')]
        for card in self.cards:
            card.changed.connect(self.inputs_changed); side.addWidget(card)
        side.addWidget(label('TIMELINE SETTINGS', 'eyebrow'))
        self.rate = QComboBox()
        for name, value in [('Match Camera A', ''), ('23.976 fps', '24000/1001'), ('24 fps', '24'),
                            ('25 fps', '25'), ('29.97 fps', '30000/1001'), ('30 fps', '30'),
                            ('50 fps', '50'), ('59.94 fps', '60000/1001'), ('60 fps', '60')]:
            self.rate.addItem(name, value)
        self.rate.currentIndexChanged.connect(self.inputs_changed)
        side.addWidget(self.rate)
        advanced = QGroupBox('Optional · Camera A search range')
        advanced.setToolTip('Limit analysis to one take. Times are seconds from the original Camera A file. Zero end searches to the file end.')
        advanced_layout = QHBoxLayout(advanced)
        self.range_start = QDoubleSpinBox(); self.range_end = QDoubleSpinBox()
        for spin, prefix in [(self.range_start, 'In '), (self.range_end, 'Out ')]:
            spin.setRange(0, 86400); spin.setDecimals(2); spin.setPrefix(prefix); spin.setSuffix('s')
            spin.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            spin.valueChanged.connect(self.inputs_changed); advanced_layout.addWidget(spin)
        side.addWidget(advanced)
        self.analyse = QPushButton('Analyse & align'); self.analyse.setObjectName('primary')
        self.analyse.clicked.connect(self.start_analysis); side.addWidget(self.analyse)
        self.cancel = QPushButton('Cancel processing'); self.cancel.setVisible(False)
        self.cancel.clicked.connect(self.cancel_job); side.addWidget(self.cancel)
        side.addStretch()
        side.addWidget(label('LOCAL BY DESIGN', 'eyebrow'))
        side.addWidget(label('Your recordings stay on this computer.\nNo uploads. No subscription. CPU analysis.', 'muted', True))
        outer.addWidget(sidebar)
        main = QVBoxLayout(); main.setContentsMargins(26, 24, 26, 18); main.setSpacing(14)
        heading = QHBoxLayout()
        title = QVBoxLayout(); title.addWidget(label('Review the performance', 'title'))
        title.addWidget(label('Listen to the master. Watch the proposed edit.', 'muted'))
        heading.addLayout(title); heading.addStretch()
        self.open_button = QPushButton('Open project'); self.open_button.clicked.connect(self.open_project)
        self.save_button = QPushButton('Save project'); self.save_button.clicked.connect(self.save_project)
        heading.addWidget(self.open_button); heading.addWidget(self.save_button); main.addLayout(heading)
        preview_frame = QFrame(); preview_frame.setObjectName('panel')
        preview_layout = QVBoxLayout(preview_frame); preview_layout.setContentsMargins(12, 10, 12, 12)
        preview_header = QHBoxLayout(); preview_header.addWidget(label('A / B COMPARISON', 'eyebrow'))
        preview_header.addStretch(); self.preview_badge = label('Master audio only', 'badge'); preview_header.addWidget(self.preview_badge)
        preview_layout.addLayout(preview_header)
        self.stack = QStackedWidget(); self.stack.setMinimumHeight(245)
        self.empty = EmptyPreview(); self.video = VideoCanvas()
        self.stack.addWidget(self.empty); self.stack.addWidget(self.video); preview_layout.addWidget(self.stack, 1)
        controls = QHBoxLayout(); self.play = QPushButton('▶'); self.play.setFixedWidth(48)
        self.play.clicked.connect(self.toggle_play); controls.addWidget(self.play)
        self.clock = label('00:00.000 / 00:00.000', 'muted'); self.clock.setMinimumWidth(168); controls.addWidget(self.clock)
        self.scrub = QSlider(Qt.Horizontal); self.scrub.setRange(0, 1000)
        self.scrub.sliderMoved.connect(self.seek); controls.addWidget(self.scrub, 1)
        self.build_preview = QPushButton('Build preview'); self.build_preview.clicked.connect(self.start_preview)
        controls.addWidget(self.build_preview); preview_layout.addLayout(controls)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self.player); self.audio.setVolume(.8)
        self.video_sink = QVideoSink(self.player)
        self.video_sink.videoFrameChanged.connect(self.video.receive_frame)
        self.player.setAudioOutput(self.audio); self.player.setVideoSink(self.video_sink)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(lambda state: self.play.setText('Ⅱ' if state == QMediaPlayer.PlayingState else '▶'))
        self.player.errorOccurred.connect(self.playback_error)
        main.addWidget(preview_frame, 4)
        summary = QHBoxLayout(); self.map_caption = label('SYNC MAP', 'eyebrow'); summary.addWidget(self.map_caption)
        summary.addStretch(); self.sections_label = label('Waiting for recordings', 'muted'); summary.addWidget(self.sections_label)
        main.addLayout(summary)
        self.timeline = Timeline(); self.timeline.seek.connect(self.seek); main.addWidget(self.timeline)
        lower = QHBoxLayout(); lower.setSpacing(14)
        tolerance_panel = QFrame(); tolerance_panel.setObjectName('panel'); tolerance_panel.setFixedWidth(254)
        tolerance_layout = QVBoxLayout(tolerance_panel)
        tolerance_layout.addWidget(label('SYNC TOLERANCE', 'eyebrow'))
        tolerance_row = QHBoxLayout(); tolerance_row.addWidget(label('±', 'title'))
        self.tolerance = QSpinBox(); self.tolerance.setRange(0, 30); self.tolerance.setValue(2); self.tolerance.setSuffix(' frames')
        self.tolerance.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        self.tolerance.valueChanged.connect(self.tolerance_changed); tolerance_row.addWidget(self.tolerance)
        tolerance_layout.addLayout(tolerance_row)
        self.tolerance_ms = label('Maximum adjustment at checked anchors', 'muted', True)
        tolerance_layout.addWidget(self.tolerance_ms)
        tolerance_layout.addWidget(label('Higher values mean fewer cuts.\nEvery musical anchor is checked, not just the ends.', 'muted', True))
        self.export_button = QPushButton('Export FCPXML…'); self.export_button.setObjectName('primary')
        self.export_button.clicked.connect(self.export_xml); tolerance_layout.addWidget(self.export_button)
        lower.addWidget(tolerance_panel)
        review_panel = QFrame(); review_panel.setObjectName('panel'); review_layout = QVBoxLayout(review_panel)
        row = QHBoxLayout(); row.addWidget(label('MUSICAL ANCHORS', 'eyebrow')); row.addStretch()
        self.review_count = label('Analysis pending', 'muted'); row.addWidget(self.review_count); review_layout.addLayout(row)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(['Master', 'Offset', 'Match', 'Review'])
        self.table.setToolTip('Match is pitch/attack similarity, not a probability. Offset maps Camera A source frames to the master. Select an anchor to seek; review exposed playing visually.')
        self.table.verticalHeader().setVisible(False); self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(125); self.table.setMaximumHeight(205)
        self.table.cellClicked.connect(lambda row, col: self.seek(int(self.project.anchors[row].master_frame/float(self.project.rate)*1000)) if self.project else None)
        review_layout.addWidget(self.table); lower.addWidget(review_panel, 1); main.addLayout(lower, 2)
        self.progress = QProgressBar(); self.progress.setRange(0, 1000); self.progress.setValue(0); self.progress.setTextVisible(False)
        main.addWidget(self.progress)
        self.status = label('Ready · add two cameras and a master audio file', 'muted', True)
        self.status.setMinimumHeight(30); main.addWidget(self.status)
        outer.addLayout(main, 1)
        self.refresh_enabled()

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def refresh_enabled(self):
        busy = self.busy()
        self.analyse.setEnabled(not busy and all(c.path for c in self.cards))
        self.cancel.setVisible(busy)
        for widget in [*self.cards, self.rate, self.range_start, self.range_end, self.open_button, self.tolerance]:
            widget.setEnabled(not busy)
        for widget in [self.export_button, self.save_button, self.build_preview]:
            widget.setEnabled(not busy and self.project is not None)
        self.play.setEnabled(bool(self.preview_path) and not busy)
        self.scrub.setEnabled(bool(self.preview_path) and not busy)

    def inputs_changed(self, *args):
        if self.loading:
            return
        if self.project:
            self.project = None; self.timeline.project = None; self.timeline.update(); self.table.setRowCount(0)
            self.sections_label.setText('Inputs changed · analyse again')
            self.invalidate_preview()
        self.refresh_enabled()

    def invalidate_preview(self):
        self.player.stop(); self.player.setSource(QUrl()); self.preview_path = None
        self.video.clear()
        self.stack.setCurrentWidget(self.empty); self.preview_badge.setText('Preview not built')
        self.play.setText('▶')

    def run_job(self, task, completed):
        self.player.stop()
        self.worker = Worker(task)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(completed)
        self.worker.error.connect(self.job_error)
        self.worker.finished.connect(self.job_finished)
        self.worker.start(); self.refresh_enabled()

    def update_progress(self, value, message):
        self.progress.setValue(int(value*1000)); self.status.setText(message)

    def job_error(self, message):
        self.status.setText(message)
        if not message.startswith('Cancelled'):
            QMessageBox.warning(self, 'TakeSync could not finish', message)

    def job_finished(self):
        self.worker.deleteLater(); self.worker = None; self.refresh_enabled()
        if self.close_pending:
            self.close()

    def cancel_job(self):
        if self.worker:
            self.worker.cancel_event.set(); self.status.setText('Cancelling safely…')

    def start_analysis(self):
        from .engine import align
        self.invalidate_preview()
        paths = [c.path for c in self.cards]
        tolerance = self.tolerance.value(); fps = self.rate.currentData() or None
        search = None
        if self.range_start.value() or self.range_end.value():
            from .media import probe
            try:
                end = self.range_end.value() or probe(paths[0], True).duration
                search = (self.range_start.value(), end)
            except Exception as exc:
                self.job_error(str(exc)); return
        self.run_job(lambda cb, cancel: align(*paths, self.cache, tolerance, fps, search, cb, cancel), self.accept_project)

    def accept_project(self, project):
        self.project = project
        self.loading = True; self.tolerance.setValue(project.tolerance); self.loading = False
        self.populate()
        project.save(self.cache/'last-session.takesync')
        self.status.setText(f'Alignment ready · camera B source offset {project.camera_delta:+.3f}s. Build a preview, or export the editable timeline.' +
                            ('  ' + ' '.join(project.warnings) if project.warnings else ''))
        self.progress.setValue(1000)

    def populate(self):
        project = self.project
        self.timeline.project = project; self.timeline.update()
        self.sections_label.setText(f'{len(project.sections)} sections  ·  {len(project.anchors)} anchors  ·  {float(project.rate):g} fps')
        review = sum(a.review for a in project.anchors)
        self.review_count.setText(f'{review} flagged for review')
        self.tolerance_ms.setText(f'±{project.tolerance/float(project.rate)*1000:.0f} ms at {float(project.rate):g} fps')
        self.table.setRowCount(len(project.anchors))
        for i, anchor in enumerate(project.anchors):
            values = [time_text(anchor.master_frame/float(project.rate)*1000),
                      f'{anchor.offset:+d} fr', f'{anchor.score:.3f}', 'Check' if anchor.review else 'Matched']
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 3:
                    item.setForeground(QColor('#e5bd72' if anchor.review else '#a0f0c2'))
                self.table.setItem(i, col, item)
        self.scrub.setRange(0, int(project.master.duration*1000))
        self.clock.setText('00:00.000 / '+time_text(project.master.duration*1000))
        self.refresh_enabled()

    def tolerance_changed(self):
        if not self.project or self.loading:
            return
        regroup(self.project, self.tolerance.value()); self.invalidate_preview(); self.populate()
        self.status.setText('Tolerance updated from cached anchors · rebuild preview to hear this edit.')

    def start_preview(self):
        from .preview import render
        self.invalidate_preview()
        self.run_job(lambda cb, cancel: render(self.project, self.cache, cancel, cb), self.accept_preview)

    def accept_preview(self, path):
        self.preview_path = str(path)
        self.stack.setCurrentWidget(self.video)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.preview_badge.setText('Preview ready · master audio')
        self.status.setText('Preview ready · press play or scrub to check the edit. Original media remains untouched.')

    def toggle_play(self):
        self.player.pause() if self.player.playbackState() == QMediaPlayer.PlayingState else self.player.play()

    def seek(self, position):
        self.player.setPosition(position)
        self.position_changed(position)

    def position_changed(self, position):
        if not self.project:
            return
        self.timeline.position = position; self.timeline.update()
        if not self.scrub.isSliderDown():
            self.scrub.setValue(position)
        self.clock.setText(time_text(position)+' / '+time_text(self.project.master.duration*1000))

    def playback_error(self, error, description):
        if error != QMediaPlayer.NoError:
            self.status.setText('Preview playback error: '+description)

    def save_project(self):
        if not self.project:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save alignment project', 'Performance.takesync', 'TakeSync project (*.takesync)')
        if path:
            try:
                self.project.save(path); self.status.setText('Project saved. The source media stays in its original location.')
            except Exception as exc:
                self.job_error(str(exc))

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open alignment project', '', 'TakeSync project (*.takesync)')
        if not path:
            return
        try:
            project = Project.load(path)
            missing = [m.path for m in [project.camera_a, project.camera_b, project.master] if not Path(m.path).is_file()]
            if missing:
                raise ValueError('Source files have moved. Restore these paths or analyse the new files:\n'+'\n'.join(missing))
            regroup(project, project.tolerance)
            self.invalidate_preview(); self.loading = True
            for card, media in zip(self.cards, [project.camera_a, project.camera_b, project.master]):
                card.set_path(media.path)
            self.loading = False; self.accept_project(project)
        except Exception as exc:
            self.loading = False; self.job_error(str(exc))

    def export_xml(self):
        from .fcpxml import export
        if not self.project:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export editable timeline', 'Performance.fcpxml', 'Final Cut Pro XML (*.fcpxml)')
        if path:
            try:
                export(self.project, path)
                self.project.save(Path(path).with_suffix('.takesync'))
                self.status.setText('FCPXML exported with both camera lanes and the continuous master. Import it into your editor.')
            except Exception as exc:
                self.job_error(str(exc))

    def closeEvent(self, event):
        if self.busy():
            self.close_pending = True; self.cancel_job(); event.ignore()
        else:
            self.player.stop(); event.accept()


def main():
    parser = argparse.ArgumentParser(description='TakeSync desktop app')
    parser.add_argument('--project', help='Open an existing .takesync session')
    parser.add_argument('--preview', help='Open a previously rendered local comparison preview')
    parser.add_argument('--screenshot', help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('TakeSync'); app.setOrganizationName('TakeSync')
    font_path = Path(__file__).parent/'assets'/'InterVariable.ttf'
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    icon = QPixmap(64, 64); icon.fill(QColor('#172b23'))
    painter = QPainter(icon); painter.setPen(QPen(QColor('#a0f0c2'), 4))
    for x, height in [(12, 14), (24, 34), (36, 23), (48, 43)]:
        painter.drawLine(x, int(32-height/2), x, int(32+height/2))
    painter.end(); app.setWindowIcon(QIcon(icon))
    window = MainWindow()
    if args.project:
        try:
            project = Project.load(args.project)
            window.loading = True
            for card, media in zip(window.cards, [project.camera_a, project.camera_b, project.master]):
                card.set_path(media.path)
            window.loading = False; window.accept_project(project)
        except Exception as exc:
            window.status.setText(str(exc))
    window.show()
    if args.preview and window.project:
        window.accept_preview(Path(args.preview).resolve())
        window.refresh_enabled()
    if args.screenshot:
        def capture():
            window.grab().save(args.screenshot)
            app.quit()
        if args.preview:
            QTimer.singleShot(250, window.player.play)
            QTimer.singleShot(700, lambda: window.player.setPosition(30000))
            QTimer.singleShot(2500, capture)
        else:
            QTimer.singleShot(1000, capture)
    sys.exit(app.exec())
