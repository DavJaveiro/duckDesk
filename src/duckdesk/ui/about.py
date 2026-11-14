"""'Sobre e licencas' dialog — text from docs/07 'Tela Sobre'."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

ABOUT_TEXT = (
    "DuckDesk: um Microduck virtual para Windows. Projeto não oficial, sem vínculo "
    "com a Pollen Robotics ou a Hugging Face.\n\n"
    "Modelo 3D do Microduck © Pollen Robotics, licenciado sob CC BY-NC-SA 4.0 "
    "(creativecommons.org/licenses/by-nc-sa/4.0), de "
    "github.com/pollen-robotics/microduck_rl, sem modificações. Descrição do robô e "
    "políticas de controle © Pollen Robotics, Apache-2.0. Atuador BAM © Rhoban, "
    "Apache-2.0. MuJoCo © Google DeepMind, Apache-2.0. Qt/PySide6, LGPLv3.\n\n"
    "Uso não comercial."
)


def notices_path() -> Path:
    # dev: repo root; frozen: alongside the exe
    for base in (Path(__file__).resolve().parents[3], Path(__import__("sys").executable).parent):
        p = base / "THIRD_PARTY_NOTICES.md"
        if p.exists():
            return p
    return Path("THIRD_PARTY_NOTICES.md")


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sobre e licenças")
        self.setModal(True)
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        text = QLabel(ABOUT_TEXT)
        text.setWordWrap(True)
        text.setTextFormat(Qt.PlainText)
        lay.addWidget(text)
        btn = QPushButton("Ver avisos completos")
        btn.clicked.connect(self._open_notices)
        lay.addWidget(btn, alignment=Qt.AlignLeft)

    def _open_notices(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(notices_path())))
