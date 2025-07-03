# -*- coding: utf-8 -*-
"""
/*************************
 Paramètres du plugin - Gestion centralisée
*************************/
"""

from qgis.PyQt.QtCore import QSettings

class SettingsManager:
    def __init__(self):
        self.settings = QSettings()
        self.prefix = "gestionnaire_pi/"

    def get_output_folder(self):
        return self.settings.value(self.prefix + "output_folder", "", type=str)

    def set_output_folder(self, path):
        self.settings.setValue(self.prefix + "output_folder", path)

    def get_styles_folder(self):
        return self.settings.value(self.prefix + "styles_folder", "", type=str)

    def set_styles_folder(self, path):
        self.settings.setValue(self.prefix + "styles_folder", path)

    def get_log_detail(self):
        return self.settings.value(self.prefix + "log_detail", False, type=bool)

    def set_log_detail(self, val):
        self.settings.setValue(self.prefix + "log_detail", val)

    # --- Theme ---
    def get_theme(self):
        return self.settings.value(self.prefix + "theme", "clair")

    def set_theme(self, theme):
        self.settings.setValue(self.prefix + "theme", theme)

    # --- Couleur ---
    def get_color(self):
        from PyQt5.QtGui import QColor
        color_str = self.settings.value(self.prefix + "color", "#f0f0f0")  # par défaut : gris doux
        return QColor(color_str)

    def set_color(self, color):
        self.settings.setValue(self.prefix + "color", color.name())  # stocke hexadécimal
