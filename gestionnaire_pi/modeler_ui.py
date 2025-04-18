from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QComboBox, QCheckBox, QHBoxLayout, QMessageBox, QLineEdit
from qgis.core import QgsProject, QgsProcessingFeedback
import processing
"""
/*************************
 run_modeleur_ui
*************************/
"""
class ModeleurDialog(QDialog):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.setWindowTitle("Création lot P.I")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        # INSEE
        self.insee_input = QLineEdit()
        layout.addWidget(QLabel("Code INSEE"))
        layout.addWidget(self.insee_input)

        # Emprises
        self.emprises_combo = QComboBox()
        layout.addWidget(QLabel("Emprises"))
        layout.addWidget(self.emprises_combo)

        # Linéaires (multiple)
        self.lineaires_combo = QComboBox()
        self.lineaires_combo.setEditable(True)
        layout.addWidget(QLabel("Linéaires (1 ou plusieurs)"))
        layout.addWidget(self.lineaires_combo)

        # Linéaires ME
        self.lineaires_me_combo = QComboBox()
        layout.addWidget(QLabel("Linéaires ME"))
        layout.addWidget(self.lineaires_me_combo)

        # Inclure classe B
        self.classe_b_checkbox = QCheckBox("Inclure classe B")
        layout.addWidget(self.classe_b_checkbox)

        # Géoréférencement
        self.georef_combo = QComboBox()
        self.georef_combo.addItems(["", "Avec X C L F"])
        layout.addWidget(QLabel("Géoréférencement"))
        layout.addWidget(self.georef_combo)

        # Dossier de sortie
        self.output_button = QPushButton("Choisir un dossier de sortie")
        self.output_button.clicked.connect(self.choose_output_folder)
        layout.addWidget(self.output_button)
        self.output_path = ""

        # Dossier styles
        self.styles_button = QPushButton("Choisir un dossier de styles (optionnel)")
        self.styles_button.clicked.connect(self.choose_styles_folder)
        layout.addWidget(self.styles_button)
        self.styles_path = ""

        # Boutons d'action
        btn_layout = QHBoxLayout()
        self.run_button = QPushButton("Exécuter")
        self.run_button.clicked.connect(self.run_model)
        btn_layout.addWidget(self.run_button)
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_button)

        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.populate_layers()

    def choose_output_folder(self):
        self.output_path = QFileDialog.getExistingDirectory(self, "Choisir un dossier de sortie")

    def choose_styles_folder(self):
        self.styles_path = QFileDialog.getExistingDirectory(self, "Choisir un dossier de styles")

    def populate_layers(self):
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            name = layer.name()
            self.emprises_combo.addItem(name)
            self.lineaires_combo.addItem(name)
            self.lineaires_me_combo.addItem(name)

    def run_model(self):
        insee = self.insee_input.text().strip()
        if not insee:
            QMessageBox.warning(self, "Erreur", "Le code INSEE est requis.")
            return

        params = {
            'insee': insee,
            'emprises': self.get_layer_by_name(self.emprises_combo.currentText()),
            'lineaires': [self.get_layer_by_name(self.lineaires_combo.currentText())],
            'lineaires_me': self.get_layer_by_name(self.lineaires_me_combo.currentText()),
            'inclure_classe_b': self.classe_b_checkbox.isChecked(),
            'georeferencement': self.georef_combo.currentIndex(),
            'dossier_sortie': self.output_path,
            'dossier_styles': self.styles_path
        }

        try:
            feedback = QgsProcessingFeedback()
            processing.run('model:Principale', params, feedback=feedback)
            QMessageBox.information(self, "Succès", "Le modèle a été exécuté avec succès.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Une erreur est survenue : {str(e)}")

    def get_layer_by_name(self, name):
        return QgsProject.instance().mapLayersByName(name)[0] if QgsProject.instance().mapLayersByName(name) else None
