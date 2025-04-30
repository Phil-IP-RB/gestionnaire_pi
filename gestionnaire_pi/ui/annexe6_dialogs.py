"""
/*************************
 annexe6_ui
*************************/
"""

from qgis.PyQt.QtWidgets import QDialog, QPushButton, QVBoxLayout, QLabel, QHBoxLayout, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt
from qgis.gui import QgsRubberBand
from qgis.core import QgsWkbTypes


class ModificationDialog(QDialog):
    def __init__(self, features, iface, deleted_features, layer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parcourir les zones")
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.layer = layer
        self.deleted_features = deleted_features
        self.features = features
        self.current_index = 0
        self.rubber_band = None

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)

        # Boutons navigation
        self.btn_prev = QPushButton("Précédent")
        self.btn_next = QPushButton("Suivant")
        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addStretch()

        # Ligne vide
        empty_spacer = QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding)

        # Boutons action
        self.btn_delete = QPushButton("🗑 Supprimer")
        self.btn_close = QPushButton("✅ Valider")
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        action_layout.addWidget(self.btn_delete)
        action_layout.addWidget(self.btn_close)
        action_layout.addStretch()

        # Layout principal
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addLayout(nav_layout)
        layout.addItem(empty_spacer)
        layout.addLayout(action_layout)
        self.setLayout(layout)

        self.btn_prev.clicked.connect(self.show_prev)
        self.btn_next.clicked.connect(self.show_next)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_close.clicked.connect(self.accept)

        self.update_view()

    def update_view(self):
        if not self.features:
            self.label.setText("Aucune zone à afficher.")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        self.current_feature = self.features[self.current_index]
        self.label.setText(f"Zone {self.current_index + 1} sur {len(self.features)} — ID: {self.current_feature.id()}")
        self.canvas.setExtent(self.current_feature.geometry().boundingBox())
        self.canvas.refresh()
        self.draw_rubber_band(self.current_feature)

        # Activer/désactiver navigation
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < len(self.features) - 1)

    def draw_rubber_band(self, feature):
        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setToGeometry(feature.geometry(), self.layer)
        self.rubber_band.setColor(Qt.red)
        self.rubber_band.setWidth(2)

    def show_next(self):
        if self.current_index < len(self.features) - 1:
            self.current_index += 1
            self.update_view()

    def show_prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_view()

    def on_delete(self):
        if not self.current_feature:
            return

        feature_id = self.current_feature.id()

        if not self.layer.isEditable():
            self.layer.startEditing()

        self.layer.deleteFeature(feature_id)
        self.deleted_features.append(self.current_feature)

        print(f"Zone supprimée immédiatement : {feature_id}")
        del self.features[self.current_index]

        if self.current_index >= len(self.features):
            self.current_index = max(0, len(self.features) - 1)

        self.update_view()

    def get_deleted_features(self):
        return self.deleted_features


class ValidationDialog(QDialog):
    def __init__(self, total_zones, length_c, length_b):
        super().__init__()
        self.setWindowTitle("Validation des Statistiques")
        self.setMinimumWidth(350)

        self.closed_by_x = False

        # Labels
        self.label_zones = QLabel(f"Nombre total de zones détectées : {total_zones}")
        self.label_c = QLabel(f"Linéaire en classe C : {length_c} m")
        self.label_b = QLabel(f"Linéaire en classe B : {length_b} m")

        # Boutons
        self.modify_button = QPushButton("Modifier")
        self.accept_button = QPushButton("✔️ Valider")
        self.cancel_button = QPushButton("❌ Annuler")

        layout = QVBoxLayout()
        layout.addWidget(self.label_zones)
        layout.addWidget(self.label_c)
        layout.addWidget(self.label_b)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.modify_button)
        btn_layout.addWidget(self.accept_button)
        btn_layout.addWidget(self.cancel_button)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.accept_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.modify_button.clicked.connect(self.modify_clicked)

        self._modify_clicked = False

    def modify_clicked(self):
        self._modify_clicked = True
        self.reject()

    def was_modify_clicked(self):
        return self._modify_clicked

    def set_modify_enabled(self, enabled: bool):
        self.modify_button.setEnabled(enabled)

    def closeEvent(self, event):
        self.closed_by_x = True
        super().closeEvent(event)
