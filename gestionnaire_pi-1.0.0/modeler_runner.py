from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QComboBox, QCheckBox, QLineEdit
from qgis.core import QgsProject, QgsProcessingFeedback
import processing

class RunCreationLotDialog(QDialog):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.setWindowTitle("Création lot P.I")

        self.layout = QVBoxLayout()

        self.insee_input = QLineEdit()
        self.layout.addWidget(QLabel("Code INSEE :"))
        self.layout.addWidget(self.insee_input)

        self.lineaires_combo = QComboBox()
        self.lineaires_combo.setEditable(True)
        self.layout.addWidget(QLabel("Linéaires :"))
        self.layout.addWidget(self.lineaires_combo)

        self.lineaires_me_combo = QComboBox()
        self.lineaires_me_combo.setEditable(True)
        self.layout.addWidget(QLabel("Linéaires ME :"))
        self.layout.addWidget(self.lineaires_me_combo)

        self.emprises_combo = QComboBox()
        self.emprises_combo.setEditable(True)
        self.layout.addWidget(QLabel("Emprises :"))
        self.layout.addWidget(self.emprises_combo)

        self.inclure_b = QCheckBox("Inclure classe B")
        self.layout.addWidget(self.inclure_b)

        self.georef_combo = QComboBox()
        self.georef_combo.addItems(["", "Avec X C L F"])
        self.layout.addWidget(QLabel("Géoréférencement :"))
        self.layout.addWidget(self.georef_combo)

        self.output_button = QPushButton("Choisir le dossier de sortie")
        self.output_button.clicked.connect(self.select_output)
        self.output_path = QLineEdit()
        self.layout.addWidget(self.output_button)
        self.layout.addWidget(self.output_path)

        self.style_button = QPushButton("Choisir le dossier des styles")
        self.style_button.clicked.connect(self.select_style)
        self.style_path = QLineEdit()
        self.layout.addWidget(self.style_button)
        self.layout.addWidget(self.style_path)

        self.run_button = QPushButton("Lancer le traitement")
        self.run_button.clicked.connect(self.run_model)
        self.layout.addWidget(self.run_button)

        self.setLayout(self.layout)

        self.populate_layers()

    def populate_layers(self):
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            name = layer.name()
            self.lineaires_combo.addItem(name)
            self.lineaires_me_combo.addItem(name)
            self.emprises_combo.addItem(name)

    def select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de sortie")
        if folder:
            self.output_path.setText(folder)

    def select_style(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de styles")
        if folder:
            self.style_path.setText(folder)

    def run_model(self):
        params = {
            'insee': self.insee_input.text(),
            'emprises': self.emprises_combo.currentText(),
            'lineaires': [self.lineaires_combo.currentText()],
            'lineaires_me': self.lineaires_me_combo.currentText(),
            'inclure_classe_b': self.inclure_b.isChecked(),
            'georeferencement': self.georef_combo.currentIndex(),
            'dossier_sortie': self.output_path.text(),
            'dossier_styles': self.style_path.text()
        }

        feedback = QgsProcessingFeedback()

        try:
            processing.run("model:Principale", params, feedback=feedback)
        except Exception as e:
            self.iface.messageBar().pushCritical("Erreur", str(e))

        self.accept()

def run_creation_lot(iface):
    dlg = RunCreationLotDialog(iface)
    dlg.exec_()
