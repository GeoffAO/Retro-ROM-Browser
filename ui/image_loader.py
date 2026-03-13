"""
Async image loader with LRU pixmap cache.

Uses a thread pool to load and scale images off the main thread,
then delivers results back via Qt signals.
"""

from pathlib import Path
from typing import Optional, Dict, Tuple
from collections import OrderedDict
import threading

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QFontMetrics, QLinearGradient

from ..core.models import get_system_color

# ── LRU Pixmap Cache ───────────────────────────────────────────────────────────

class PixmapLRUCache:
    """Thread-safe LRU cache for scaled QPixmaps."""

    def __init__(self, max_size: int = 600):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._max = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[QPixmap]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def put(self, key: str, pm: QPixmap):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                self._cache[key] = pm
                if len(self._cache) > self._max:
                    self._cache.popitem(last=False)

    def clear(self):
        with self._lock:
            self._cache.clear()


# Singleton cache shared across the app
IMAGE_CACHE = PixmapLRUCache(max_size=800)

# Placeholder cache — keyed by (w, h, system) — these are cheap to keep forever
PLACEHOLDER_CACHE: Dict[Tuple, QPixmap] = {}


# ── Placeholder Generator ──────────────────────────────────────────────────────

def make_placeholder(w: int, h: int, title: str, system: str) -> QPixmap:
    """Render a styled placeholder cover for ROMs with no image."""
    key = (w, h, system)
    # Use a per-system cached base and just reuse it (title ignored for perf)
    if key in PLACEHOLDER_CACHE:
        base = PLACEHOLDER_CACHE[key]
        # Stamp title on a copy
        pm = QPixmap(base)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        title_font = QFont("Segoe UI", max(7, w // 16))
        painter.setFont(title_font)
        painter.setPen(QPen(QColor("#c0d8e8")))
        fm = QFontMetrics(title_font)
        words = title.split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            if fm.horizontalAdvance(test) <= w - 12:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        lines = lines[:4]
        line_h = fm.height() + 2
        y_start = (h - len(lines) * line_h) // 2
        for i, line in enumerate(lines):
            painter.drawText(6, y_start + i * line_h, w - 12, line_h,
                             Qt.AlignmentFlag.AlignHCenter, line)
        painter.end()
        return pm

    # Build base (system name, gradient, border only)
    color_hex = get_system_color(system)
    base_pm = QPixmap(w, h)
    base_pm.fill(QColor(0, 0, 0, 0))
    painter = QPainter(base_pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    base_col = QColor(color_hex)
    grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0, base_col.darker(300))
    grad.setColorAt(1, QColor("#0a0c14"))
    painter.fillRect(0, 0, w, h, grad)
    painter.setPen(QPen(base_col.lighter(120), 1))
    painter.drawRect(1, 1, w - 2, h - 2)

    sys_font = QFont("Segoe UI", max(7, w // 14), QFont.Weight.Bold)
    painter.setFont(sys_font)
    painter.setPen(QPen(base_col.lighter(180)))
    painter.drawText(0, 8, w, 20, Qt.AlignmentFlag.AlignHCenter, system.upper())
    painter.end()

    PLACEHOLDER_CACHE[key] = base_pm

    # Recurse once to stamp the title on the cached base
    return make_placeholder(w, h, title, system)


# ── Async Load Runnable ────────────────────────────────────────────────────────

class _ImageSignals(QObject):
    loaded = pyqtSignal(str, QPixmap)   # cache_key, pixmap


class ImageLoadRunnable(QRunnable):
    """Loads and scales one image off the main thread."""

    def __init__(self, cache_key: str, path: Path, target_w: int, target_h: int):
        super().__init__()
        self.setAutoDelete(True)
        self.cache_key = cache_key
        self.path = path
        self.target_w = target_w
        self.target_h = target_h
        self.signals = _ImageSignals()

    @pyqtSlot()
    def run(self):
        # Check cache first (another thread may have beaten us)
        if IMAGE_CACHE.get(self.cache_key):
            pm = IMAGE_CACHE.get(self.cache_key)
            self.signals.loaded.emit(self.cache_key, pm)
            return

        try:
            pm = QPixmap(str(self.path))
            if pm.isNull():
                return
            pm = pm.scaled(
                self.target_w, self.target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            IMAGE_CACHE.put(self.cache_key, pm)
            self.signals.loaded.emit(self.cache_key, pm)
        except Exception:
            pass


# ── Loader Manager ─────────────────────────────────────────────────────────────

class ImageLoader(QObject):
    """
    Manages a QThreadPool for async image loading.
    Consumers connect to `image_ready` to receive results.
    """

    image_ready = pyqtSignal(str, QPixmap)   # cache_key, pixmap

    _instance: Optional["ImageLoader"] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(4)

    @classmethod
    def instance(cls) -> "ImageLoader":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def request(self, path: Path, target_w: int, target_h: int) -> str:
        """
        Request an image load. Returns the cache key immediately.
        If already cached, emits image_ready synchronously via queued connection.
        """
        cache_key = f"{path}:{target_w}x{target_h}"

        cached = IMAGE_CACHE.get(cache_key)
        if cached:
            # Emit asynchronously so caller has time to connect
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.image_ready.emit(cache_key, cached))
            return cache_key

        runnable = ImageLoadRunnable(cache_key, path, target_w, target_h)
        runnable.signals.loaded.connect(self.image_ready)
        self._pool.start(runnable)
        return cache_key

    def clear_cache(self):
        IMAGE_CACHE.clear()
        PLACEHOLDER_CACHE.clear()
