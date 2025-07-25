from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog, QColorDialog, QFontDialog
from PyQt5.QtGui import QColor, QFont
import os

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'gestionnaire_pi_settings.ui'))


class GestionnairePiSettingsDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.settings = QSettings()

        self.load_settings()

        self.btn_browse_output.clicked.connect(self.select_output_folder)
        self.btn_browse_styles.clicked.connect(self.select_styles_folder)
        self.btn_select_color.clicked.connect(self.select_color)
        self.btn_select_font.clicked.connect(self.select_font)
        self.buttonBox.accepted.connect(self.save_settings)
        self.buttonBox.rejected.connect(self.reject)

    def load_settings(self):
        self.line_default_output.setText(self.settings.value("gestionnaire_pi/default_output", ""))
        self.line_default_styles.setText(self.settings.value("gestionnaire_pi/default_styles", ""))
        self.check_log_detail.setChecked(self.settings.value("gestionnaire_pi/log_detail", False, type=bool))

        color = QColor(self.settings.value("gestionnaire_pi/ui_color", "#000000"))
        self.label_color.setStyleSheet(f"background-color: {color.name()}")

        font_str = self.settings.value("gestionnaire_pi/ui_font", "")
        if font_str:
            font = QFont()
            font.fromString(font_str)
            self.label_font.setFont(font)
            self.label_font.setText(font.family())

    def save_settings(self):
        self.settings.setValue("gestionnaire_pi/default_output", self.line_default_output.text())
        self.settings.setValue("gestionnaire_pi/default_styles", self.line_default_styles.text())
        self.settings.setValue("gestionnaire_pi/log_detail", self.check_log_detail.isChecked())

        font = self.label_font.font()
        self.settings.setValue("gestionnaire_pi/ui_font", font.toString())

        color = self.label_color.palette().color(self.label_color.backgroundRole())
        self.settings.setValue("gestionnaire_pi/ui_color", color.name())

        self.accept()

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de sortie par défaut")
        if folder:
            self.line_default_output.setText(folder)

    def select_styles_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de styles par défaut")
        if folder:
            self.line_default_styles.setText(folder)

    def select_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.label_color.setStyleSheet(f"background-color: {color.name()}")

    def select_font(self):
        font, ok = QFontDialog.getFont()
        if ok:
            self.label_font.setFont(font)
            self.label_font.setText(font.family())
