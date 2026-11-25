
import sys
import json
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame,
    QStackedWidget, QLineEdit, QSpinBox,
    QComboBox, QCheckBox
)

from pynput import keyboard, mouse
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController

APP_NAME = "7X MACRO MENU"

CONFIG_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT = {
    "litefoot": {
        "keys": ["scroll down", "e", "q"],
        "delays": [45, 45, 45, 35],
        "mode": "Ao segurar Mouse 2"
    },
    "correr": {
        "interval": 70,
        "enabled": True
    }
}

def load_config():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg = json.loads(json.dumps(DEFAULT))
            for section in cfg:
                cfg[section].update(data.get(section, {}))
            return cfg
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT))

def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

def to_key(value):
    value = value.lower().strip()

    special = {
        "space": Key.space,
        "enter": Key.enter,
        "shift": Key.shift,
        "ctrl": Key.ctrl,
        "alt": Key.alt,
        "tab": Key.tab,
        "esc": Key.esc,
        "backspace": Key.backspace,
        "up": Key.up,
        "down": Key.down,
        "left": Key.left,
        "right": Key.right
    }

    if value in special:
        return special[value]

    if value.startswith("f") and value[1:].isdigit():
        return getattr(Key, value, None)

    return value[0] if value else "e"

class Signals(QObject):
    status = Signal(str)

class KeyCapture(QLineEdit):
    def __init__(self, value=""):
        super().__init__()
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        self.setText(value.upper())
        self.setPlaceholderText("CLIQUE E PRESSIONE UMA TECLA")
        self.waiting = False

    def mousePressEvent(self, event):
        self.waiting = True
        self.setText("PRESSIONE A TECLA...")
        event.accept()

    def keyPressEvent(self, event):
        if not self.waiting:
            return

        k = event.key()

        names = {
            Qt.Key_Space: "space",
            Qt.Key_Return: "enter",
            Qt.Key_Enter: "enter",
            Qt.Key_Tab: "tab",
            Qt.Key_Escape: "esc",
            Qt.Key_Backspace: "backspace",
            Qt.Key_Up: "up",
            Qt.Key_Down: "down",
            Qt.Key_Left: "left",
            Qt.Key_Right: "right"
        }

        if k in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta):
            return

        if k in names:
            value = names[k]
        elif Qt.Key_F1 <= k <= Qt.Key_F24:
            value = "f" + str(k - Qt.Key_F1 + 1)
        else:
            value = event.text().lower()

        if value:
            self.waiting = False
            self.setText(value.upper())

class App(QMainWindow):
    def __init__(self):
        super().__init__()

        self.cfg = load_config()
        self.kb = KeyboardController()
        self.ms = MouseController()

        self.held = set()
        self.busy = False
        self.stop = threading.Event()

        self.sig = Signals()
        self.sig.status.connect(self.update_status)

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(760, 520)

        self.setStyleSheet("""
        QWidget {
            background:#101010;
            color:#eee;
            font-family:Segoe UI;
        }
        QFrame#panel {
            background:#191919;
            border:1px solid #303030;
            border-radius:12px;
        }
        QLabel#title {
            color:#f4c400;
            font-size:25px;
            font-weight:800;
        }
        QLabel#section {
            color:#f4c400;
            font-size:17px;
            font-weight:700;
        }
        QLabel#sub {
            color:#999;
            font-size:12px;
        }
        QPushButton {
            background:#252525;
            border:1px solid #3a3a3a;
            border-radius:8px;
            padding:10px;
            font-weight:600;
        }
        QPushButton:hover {
            border:1px solid #f4c400;
        }
        QPushButton#active {
            background:#f4c400;
            color:#111;
            border:0;
        }
        QLineEdit,QSpinBox,QComboBox {
            background:#222;
            border:1px solid #414141;
            border-radius:7px;
            padding:8px;
            color:white;
        }
        """)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)

        side = QFrame()
        side.setObjectName("panel")
        side.setFixedWidth(190)
        sl = QVBoxLayout(side)

        brand = QLabel("7X\nMACRO MENU")
        brand.setStyleSheet(
            "color:#f4c400;font-size:22px;font-weight:900"
        )
        sl.addWidget(brand)
        sl.addSpacing(20)

        self.nav = []

        for i, name in enumerate(["INÍCIO", "LITE FOOT", "CORRER"]):
            button = QPushButton(name)
            button.clicked.connect(
                lambda checked=False, x=i: self.pages.setCurrentIndex(x)
            )
            sl.addWidget(button)
            self.nav.append(button)

        sl.addStretch()
        sl.addWidget(QLabel("MTA • MACROS"))
        outer.addWidget(side)

        right = QVBoxLayout()

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        right.addWidget(title)

        subtitle = QLabel("Painel de configuração de macros")
        subtitle.setObjectName("sub")
        right.addWidget(subtitle)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.home())
        self.pages.addWidget(self.lite())
        self.pages.addWidget(self.runpage())

        right.addWidget(self.pages, 1)

        self.status = QLabel("Status: pronto")
        self.status.setStyleSheet("color:#f4c400")
        right.addWidget(self.status)

        outer.addLayout(right, 1)

        self.pages.currentChanged.connect(self.update_nav)

        self.k_listener = keyboard.Listener(
            on_press=self.keydown,
            on_release=self.keyup
        )
        self.k_listener.start()

        self.m_listener = mouse.Listener(on_click=self.click)
        self.m_listener.start()

        threading.Thread(
            target=self.run_loop,
            daemon=True
        ).start()

    def panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        return frame, layout

    def home(self):
        frame, layout = self.panel()

        layout.addWidget(QLabel("BEM-VINDO AO 7X", objectName="section"))
        layout.addWidget(QLabel("Lite Foot: sequência de 4 etapas."))
        layout.addWidget(QLabel("Correr: scroll enquanto W/A/S/D estiver pressionado."))
        layout.addWidget(QLabel("As configurações são salvas automaticamente."))
        layout.addStretch()

        return frame

    def lite(self):
        frame, layout = self.panel()

        layout.addWidget(QLabel("LITE FOOT", objectName="section"))
        layout.addWidget(QLabel(
            "Clique no campo e pressione a tecla desejada."
        ))

        keys = self.cfg["litefoot"]["keys"]
        delays = self.cfg["litefoot"]["delays"]

        self.key_fields = []
        self.delay_fields = []

        names = [
            "ETAPA 1 — SCROLL DOWN",
            "ETAPA 2",
            "ETAPA 3",
            "ETAPA 4 — SOCO (MOUSE 1)"
        ]

        for i, name in enumerate(names):
            row = QHBoxLayout()
            row.addWidget(QLabel(name))

            if i < 3:
                field = KeyCapture(keys[i])
                self.key_fields.append(field)
                row.addWidget(field, 1)
            else:
                fixed = QLabel("CLIQUE DO MOUSE ESQUERDO")
                fixed.setAlignment(Qt.AlignCenter)
                row.addWidget(fixed, 1)

            spin = QSpinBox()
            spin.setRange(0, 2000)
            spin.setSuffix(" ms")
            spin.setValue(delays[i])

            self.delay_fields.append(spin)
            row.addWidget(spin)

            layout.addLayout(row)

        layout.addWidget(QLabel("Ativação"))

        self.mode = QComboBox()
        self.mode.addItems([
            "Ao segurar Mouse 2",
            "Um ciclo por clique direito"
        ])
        self.mode.setCurrentText(self.cfg["litefoot"]["mode"])
        layout.addWidget(self.mode)

        button = QPushButton("SALVAR CONFIGURAÇÕES")
        button.setObjectName("active")
        button.clicked.connect(self.save_lite)
        layout.addWidget(button)

        layout.addStretch()
        return frame

    def runpage(self):
        frame, layout = self.panel()

        layout.addWidget(QLabel("CORRER", objectName="section"))
        layout.addWidget(QLabel(
            "Envia scroll para cima enquanto uma tecla de movimento estiver pressionada."
        ))

        row = QHBoxLayout()
        row.addWidget(QLabel("Intervalo entre scrolls:"))

        self.interval = QSpinBox()
        self.interval.setRange(10, 1000)
        self.interval.setSuffix(" ms")
        self.interval.setValue(self.cfg["correr"]["interval"])

        row.addWidget(self.interval)
        layout.addLayout(row)

        self.enabled = QCheckBox("Ativar macro Correr")
        self.enabled.setChecked(self.cfg["correr"]["enabled"])
        layout.addWidget(self.enabled)

        button = QPushButton("SALVAR CONFIGURAÇÕES")
        button.setObjectName("active")
        button.clicked.connect(self.save_run)
        layout.addWidget(button)

        layout.addStretch()
        return frame

    def update_nav(self, index):
        for i, button in enumerate(self.nav):
            button.setObjectName("active" if i == index else "")
            button.style().unpolish(button)
            button.style().polish(button)

    def update_status(self, message):
        self.status.setText("Status: " + message)

    def save_lite(self):
        self.cfg["litefoot"] = {
            "keys": [field.text().lower() for field in self.key_fields],
            "delays": [field.value() for field in self.delay_fields],
            "mode": self.mode.currentText()
        }
        save_config(self.cfg)
        self.update_status("Lite Foot salvo")

    def save_run(self):
        self.cfg["correr"] = {
            "interval": self.interval.value(),
            "enabled": self.enabled.isChecked()
        }
        save_config(self.cfg)
        self.update_status("Correr salvo")

    def keydown(self, key):
        try:
            self.held.add(key.char.lower())
        except Exception:
            self.held.add(str(key).replace("Key.", "").lower())

    def keyup(self, key):
        try:
            self.held.discard(key.char.lower())
        except Exception:
            self.held.discard(str(key).replace("Key.", "").lower())

    def click(self, x, y, button, pressed):
        if button == Button.right and pressed and not self.busy:
            threading.Thread(
                target=self.sequence,
                daemon=True
            ).start()

    def send(self, value):
        value = value.lower().strip()

        if value == "scroll down":
            self.ms.scroll(0, -1)
            return

        if value == "scroll up":
            self.ms.scroll(0, 1)
            return

        key = to_key(value)

        try:
            self.kb.press(key)
            self.kb.release(key)
        except Exception:
            pass

    def sequence(self):
        self.busy = True

        try:
            keys = self.cfg["litefoot"]["keys"]
            delays = self.cfg["litefoot"]["delays"]

            for i in range(4):
                if i < 3:
                    self.send(keys[i])
                else:
                    self.ms.press(Button.left)
                    time.sleep(0.025)
                    self.ms.release(Button.left)

                time.sleep(delays[i] / 1000)

            self.sig.status.emit("Lite Foot executado")

        finally:
            self.busy = False

    def run_loop(self):
        while not self.stop.is_set():
            try:
                config = self.cfg["correr"]
                delay = max(10, config["interval"]) / 1000

                if config["enabled"] and any(
                    key in self.held for key in ("w", "a", "s", "d")
                ):
                    self.ms.scroll(0, 1)
                    time.sleep(delay)
                else:
                    time.sleep(0.01)

            except Exception:
                time.sleep(0.1)

    def closeEvent(self, event):
        self.stop.set()
        self.k_listener.stop()
        self.m_listener.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = App()
    window.show()
    sys.exit(app.exec())
