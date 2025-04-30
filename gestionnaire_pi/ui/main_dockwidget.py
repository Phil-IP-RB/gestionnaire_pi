from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsProcessingFeedback,
    QgsProcessingContext,
)
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt, QTimer
import processing
import os
from PyQt5.QtWidgets import QColorDialog, QFontDialog
from PyQt5.QtGui import QFont
from qgis.PyQt.QtCore import QSettings
from gestionnaire_pi.settings.manager import SettingsManager

"""
/*************************
 gestionnaire_pi_dockwidget
*************************/
"""
FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'main_dockwidget.ui'))

class CustomFeedback(QgsProcessingFeedback):
    def __init__(self, log_widget):
        super().__init__()
        self.log_widget = log_widget

    def pushInfo(self, info):
        super().pushInfo(info)
        self._log(info)

    def pushWarning(self, warning):
        super().pushWarning(warning)
        self._log(f"[WARNING] {warning}")

    def reportError(self, error, fatalError=False):
        super().reportError(error, fatalError)
        self._log(f"[ERROR] {error}")

    def setProgress(self, progress):
        super().setProgress(progress)
        self._log(f"[Progression] {progress:.1f}%")

    def _log(self, message):
        if self.log_widget:
            self.log_widget.append(message)

class GestionnairePiDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    closingPlugin = pyqtSignal()

    def __init__(self, plugin):
        super(GestionnairePiDockWidget, self).__init__(None)
        self.setupUi(self)
        self.settings = SettingsManager()
        self.current_color = self.settings.get_color()
        self.plugin = plugin
        self.settings = SettingsManager()

        # Connexions menu principal
        self.btn_creation_lot.clicked.connect(self.show_creation_lot_menu)
        self.btn_annexe6.clicked.connect(self.show_annexe6_menu)
        self.btn_parametres.clicked.connect(self.show_settings)

        # Connexions Annexe 6
        self.btn_annexe6_retour.clicked.connect(self.show_main_menu)
        self.btn_browse_folder.clicked.connect(self.select_output_folder)
        self.btn_annexe6_lancer.clicked.connect(self.run_annexe6_from_ui)
        self.combo_georef.addItems(["", "Avec X C L F"])

        # Connexions Création Lot PI
        self.selected_line_layers = []
        self.btn_select_line_layers.clicked.connect(self.select_line_layers_dialog)
        self.btn_retour_creation_lot.clicked.connect(self.show_main_menu)
        self.btn_browse_output.clicked.connect(self.select_output_folder_lot)
        self.btn_browse_styles.clicked.connect(self.select_styles_folder)
        self.btn_lancer_creation_lot.clicked.connect(self.run_creation_lot)

        # Connexions paramètres
        self.btn_browse_default_output.clicked.connect(self.select_default_output_folder)
        self.btn_browse_default_styles.clicked.connect(self.select_default_styles_folder)
        self.btn_choose_color.clicked.connect(self.select_color)
        self.btn_save_settings.clicked.connect(self.save_settings)
        self.btn_param_retour.clicked.connect(self.show_main_menu)

        self.combo_theme = self.findChild(QtWidgets.QComboBox, "combo_theme")
        if self.combo_theme:
            self.combo_theme.currentTextChanged.connect(self.apply_theme)

        self.load_settings()

    def show_main_menu(self):
        self.stackedWidget.setCurrentWidget(self.page_main_menu)

    def show_annexe6_menu(self):
        self.stackedWidget.setCurrentWidget(self.page_annexe6)
        self.populate_layer_combos()
        self.line_output_folder.setText(self.settings.get_output_folder())

    def show_creation_lot_menu(self):
        self.stackedWidget.setCurrentWidget(self.page_creation_lot)
        self.populate_creation_lot_combos()
        self.line_output.setText(self.settings.get_output_folder())
        self.line_styles.setText(self.settings.get_styles_folder())

    def populate_layer_combos(self):
        self.combo_troncons.clear()
        self.combo_zones.clear()
        self.combo_folios.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                geom = QgsWkbTypes.geometryType(layer.wkbType())
                if geom == QgsWkbTypes.LineGeometry:
                    self.combo_troncons.addItem(layer.name())
                elif geom == QgsWkbTypes.PolygonGeometry:
                    self.combo_zones.addItem(layer.name())
                    self.combo_folios.addItem(layer.name())

    def populate_creation_lot_combos(self):
        self.combo_emprises.clear()
        self.combo_lineaires_me.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                geom = QgsWkbTypes.geometryType(layer.wkbType())
                if geom == QgsWkbTypes.PolygonGeometry:
                    self.combo_emprises.addItem(layer.name())
                elif geom == QgsWkbTypes.LineGeometry:
                    self.combo_lineaires_me.addItem(layer.name())

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de sortie")
        if folder:
            self.line_output_folder.setText(folder)

    def select_output_folder_lot(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de sortie")
        if folder:
            self.line_output.setText(folder)

    def run_annexe6_from_ui(self):
        from gestionnaire_pi.core.annexe6.controller import Annexe6Processor
        proc = Annexe6Processor(self.plugin.iface)
        proc.run_custom(
            self.combo_troncons.currentText(),
            self.combo_zones.currentText(),
            self.combo_folios.currentText(),
            self.line_output_folder.text()
        )

    def run_creation_lot(self):
        self.progress_msg = QMessageBox(self)
        self.progress_msg.setWindowTitle("Traitement en cours")
        self.progress_msg.setText("Le traitement est en cours...\nVeuillez patienter.")
        self.progress_msg.setIcon(QMessageBox.Information)
        self.progress_msg.setStandardButtons(QMessageBox.NoButton)
        self.progress_msg.setModal(False)
        self.progress_msg.show()
        QTimer.singleShot(100, self._start_sync_processing)

    def _start_sync_processing(self):
        try:
            # 1. Récupération des paramètres utilisateurs
            params = {
                'insee': self.line_insee.text(),
                'emprises': self._layer_by_name(self.combo_emprises.currentText()),
                'lineaires': self.selected_line_layers,
                'lineaires_me': self._layer_by_name(self.combo_lineaires_me.currentText()),
                'inclure_classe_b': self.inclure_classe_b.isChecked(),
                'georeferencement': self.combo_georef.currentIndex(),
                'dossier_sortie': self.line_output.text(),
                'dossier_styles': self.line_styles.text()
            }

            # On choisit l'ID qui a été affiché à l'initGui :
            alg_id = 'gestionnaire_pi_models:Principale'  

            feedback = QgsProcessingFeedback()
            outputs = processing.runAndLoadResults(alg_id, params, feedback=feedback)

            # Fermeture et infos
            if self.progress_msg:
                self.progress_msg.accept()
            QMessageBox.information(self, "Succès",
                "Création du lot P.I terminée et résultats chargés.")

        except Exception as e:
            if self.progress_msg:
                self.progress_msg.accept()
            QMessageBox.critical(self, "Erreur durant le traitement", str(e))

    def _layer_by_name(self, name):
        return QgsProject.instance().mapLayersByName(name)[0] if name else None

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

    def show_settings(self):
        self.stackedWidget.setCurrentWidget(self.page_parametres)

    def load_settings(self):
        self.line_default_output.setText(self.settings.get_output_folder())
        self.line_default_styles.setText(self.settings.get_styles_folder())
        self.check_logs.setChecked(self.settings.get_log_detail())
        self.current_color = self.settings.get_color()
        self.setStyleSheet(f"background-color: {self.current_color.name()};")
        if hasattr(self, "label_color"):
            self.label_color.setStyleSheet(f"background-color: {self.current_color.name()}")

        if self.combo_theme:
            theme = self.settings.get_theme()
            index = self.combo_theme.findText(theme)
            self.combo_theme.setCurrentIndex(index if index >= 0 else 0)
            self.apply_theme(theme)

    def save_settings(self):
        self.settings.set_output_folder(self.line_default_output.text())
        self.settings.set_styles_folder(self.line_default_styles.text())
        self.settings.set_log_detail(self.check_logs.isChecked())
        self.settings.set_color(self.current_color)

        if self.combo_theme:
            self.settings.set_theme(self.combo_theme.currentText())

    def select_default_output_folder(self):
        """Ouvre un dialogue pour sélectionner le dossier de sortie."""
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de sortie")
        if folder:
            self.line_default_output.setText(folder)

    def select_default_styles_folder(self):
        """Ouvre un dialogue pour sélectionner le dossier des styles."""
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier des styles")
        if folder:
            self.line_default_styles.setText(folder)

    def select_color(self):
        color = QColorDialog.getColor(initial=self.current_color)
        if color.isValid():
            self.current_color = color  # ✅ on stocke dans l'objet
            self.setStyleSheet(f"background-color: {color.name()};")
            if hasattr(self, "label_color"):
                self.label_color.setStyleSheet(f"background-color: {color.name()}")

    def select_styles_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier des styles")
        if folder:
            self.line_styles.setText(folder)

    def apply_theme(self, theme):
        if theme == "Thème sombre":
            self.setStyleSheet("""
                QDockWidget {
                    background-color: #2e2e2e;
                    color: #ffffff;
                }
                QWidget {
                    background-color: #2e2e2e;
                    color: #ffffff;
                }
                QLineEdit, QComboBox, QTextEdit, QTreeWidget {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555;
                }
                QPushButton {
                    background-color: #444;
                    color: white;
                }
                QCheckBox {
                    color: white;
                }
            """)
        else:
            self.setStyleSheet("""
                QDockWidget {
                    background-color: #f0f0f0;
                    color: #000000;
                }
                QWidget {
                    background-color: #f0f0f0;
                    color: #000000;
                }
                QLineEdit, QComboBox, QTextEdit, QTreeWidget {
                    background-color: #ffffff;
                    color: #000000;
                    border: 1px solid #ccc;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: black;
                }
                QCheckBox {
                    color: black;
                }
            """)


    def select_line_layers_dialog(self):
        layers = [
            layer for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.LineGeometry
        ]

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Sélectionner les linéaires")
        layout = QtWidgets.QVBoxLayout(dialog)

        checkboxes = []
        for layer in layers:
            cb = QtWidgets.QCheckBox(layer.name())
            cb.setChecked(layer.name() in [l.name() for l in self.selected_line_layers])
            layout.addWidget(cb)
            checkboxes.append((cb, layer))

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(btns)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)

        if dialog.exec_():
            self.selected_line_layers = [layer for cb, layer in checkboxes if cb.isChecked()]
            count = len(self.selected_line_layers)
            self.line_selected_layers.setText(f"{count} couche(s) sélectionnée(s)" if count else "Aucune couche sélectionnée")
