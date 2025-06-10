# --- Standard library -------------------------------------------------
import os
import re, time
from urllib.parse import unquote  # au cas où il y ait des espaces encodés
import random

# --- QGIS / Qt --------------------------------------------------------
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal, Qt, QMetaObject, QTimer, QDir
from qgis.PyQt.QtGui import QMovie

from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QLabel,
    QDialog,
    QVBoxLayout,
    QMessageBox,
)
from qgis.core import (
    QgsApplication, QgsMessageLog, QgsProcessingAlgRunnerTask,
    QgsProcessingContext, QgsProcessingFeedback, QgsProject,
    QgsRasterLayer, QgsSettings, QgsVectorLayer,
    QgsWkbTypes, Qgis, QgsPathResolver,    
)
from qgis import processing

from PyQt5.QtWidgets import QWidget, QFrame, QLabel, QHBoxLayout, QSizePolicy
from PyQt5.QtGui import QMovie
from PyQt5.QtCore import Qt, QSize, QTimer

# --- Plugin local -----------------------------------------------------
from gestionnaire_pi.settings.manager import SettingsManager
import gestionnaire_pi.resources_rc

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "main_dockwidget.ui")
)

class TimingFeedback(QgsProcessingFeedback):
    """Enregistre la durée de chaque algorithme et relaie *tous* les messages
    (Running, Parameters, Results, finished…) dans l’onglet « GestionnairePi » du
    panneau de logs QGIS.
    """
    _re_start = re.compile(r"^Running (.+)")
    _re_end   = re.compile(r"^Algorithm '([^']+)' finished")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._t0: dict[str, float] = {}
        self.times: dict[str, float] = {}
        self._log: list[str] = []        # journal interne

    # ---------- utilitaire interne ----------
    def _log_to_qgis(self, txt: str) -> None:
        # QgsMessageLog.logMessage(f"[GestionnairePi] ► {txt}",
                                 # "GestionnairePi", Qgis.Info)
        return

    def _handle(self, txt: str) -> None:
        self._log.append(txt)
        if m := self._re_start.match(txt):
            self._t0[m.group(1)] = time.perf_counter()
        elif m := self._re_end.match(txt):
            algo = m.group(1)
            if algo in self._t0:
                self.times[algo] = time.perf_counter() - self._t0.pop(algo)

    # ---------- méthodes surchargées ----------
    def info(self, txt: str) -> None:
        self._handle(txt)
        self._log_to_qgis(txt)
        super().info(txt)

    def pushCommandInfo(self, txt: str) -> None:
        self._handle(txt)
        self._log_to_qgis(txt)
        super().pushCommandInfo(txt)

    def pushDebugInfo(self, txt: str) -> None:
        self._handle(txt)
        self._log_to_qgis(txt)
        super().pushDebugInfo(txt)

    # ---------- accès rapide ----------
    def text(self, n: int = 10) -> str:
        """Retourne les *n* derniers messages du log interne."""
        return "\n".join(self._log[-n:])

class ProgressLineWebp(QWidget):
    """
    Barre façon YouTube :
      – piste grise pleine largeur (4 px) centrée verticalement
      – barre rouge qui se remplit
      – curseur animé WEBP **redimensionné à max 64 px**
    API : set_progress(float 0-100)
    """

    def __init__(self, webp_path: str, parent=None):
        super().__init__(parent)

        # --- piste grise -----------------------------------------------------
        self._track = QFrame(self)
        self._track.setFixedHeight(4)
        self._track.setStyleSheet("background:#009bc4;border:none;")

        # --- barre rouge (progression) --------------------------------------
        self._bar = QFrame(self)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet("background:#fab200;border:none;")

        # --- curseur animé ---------------------------------------------------
        self._thumb = QLabel(self)
        self._movie = QMovie(webp_path, parent=self)
        self._movie.setCacheMode(QMovie.CacheAll)
        self._movie.setScaledSize(QSize(32, 32))      # ① limite à 32 px
        self._movie.start()

        self._thumb.setStyleSheet("background: transparent;")

        pix = self._movie.currentPixmap()
        # taille de repli si le WEBP n’est pas encore décodé
        self._thumb.setFixedSize(pix.size() if not pix.isNull() else QSize(24, 24))
        self._thumb.setMovie(self._movie)

        # widget : hauteur = curseur ou 8 px mini
        self.setMinimumHeight(max(self._thumb.height(), 8))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._pct = 0
        self._thumb_offset = -5
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)   # 60 fps
        self._timer.setInterval(16)
        self._target_pct = 0
        self.set_progress(0)
        


    # ------------------------------------------------------------------------
    #  API publique
    # ------------------------------------------------------------------------
    def set_progress(self, pct: float):
        """Reçoit la valeur cible (0-100). L’animation se fait dans _tick()."""
        self._target_pct = max(0.0, min(100.0, pct))
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        """Interpole en douceur vers _target_pct puis met à jour la géométrie."""
        # incrément progressif : 6 % par frame max (≈ 0,1 s pour rattraper 100 %)
        step = 6 / 60
        if abs(self._pct - self._target_pct) < step:
            self._pct = self._target_pct
            self._timer.stop()               # cible atteinte → stop animation
        else:
            self._pct += step if self._pct < self._target_pct else -step

        # --- mise à jour visuelle ----------------------------------------
        total_w = self.width()
        thumb_w = self._thumb.width()
        y       = (self.height() - 4) // 2
        bar_w   = int(self._pct / 100 * total_w)

        self._track.setGeometry(0, y, total_w, 4)
        self._bar.setGeometry(0, y, bar_w, 4)

        x_thumb = int(self._pct / 100 * (total_w - thumb_w))
        y_thumb = (self.height() - self._thumb.height()) // 2 + self._thumb_offset
        self._thumb.move(x_thumb, y_thumb)


    # ------------------------------------------------------------------------
    #  resizeEvent : on ré-applique la position courante
    # ------------------------------------------------------------------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.set_progress(self._pct)
        
class GestionnairePiDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    """Dock principal du plugin Gestionnaire P.I."""

    closingPlugin = pyqtSignal()
    _task_signals_connected = False
    _layers_signals_connected = False

    # ────────────────────────────── INIT ──────────────────────────────
    def __init__(self, plugin):
        super().__init__(None)
        self.setupUi(self)
        self.plugin = plugin
        self.settings = SettingsManager()
        self.current_color = self.settings.get_color()

        self.current_task: QgsProcessingAlgRunnerTask | None = None
        self.current_context: QgsProcessingContext | None = None
        self._task_start_time: float | None = None

        # Au moins 1 thread Processing
        qs = QgsSettings()
        if qs.value("processing/threads", 1, type=int) < 2:
            qs.setValue("processing/threads", 2)

        # Connexions uniques (TaskManager & Project)
        if not GestionnairePiDockWidget._task_signals_connected:
            QgsApplication.taskManager().allTasksFinished.connect(self._on_all_tasks_finished)
            GestionnairePiDockWidget._task_signals_connected = True

        if not GestionnairePiDockWidget._layers_signals_connected:
            prj = QgsProject.instance()
            prj.layersAdded.connect(self._on_layers_changed)
            prj.layersWillBeRemoved.connect(self._on_layers_changed)
            GestionnairePiDockWidget._layers_signals_connected = True

        # Préremplissage UI
        self.populate_layer_combos()
        self.populate_creation_lot_combos()

        # Connexions UI
        self.btn_creation_lot.clicked.connect(self.show_creation_lot_menu)
        self.btn_annexe6.clicked.connect(self.show_annexe6_menu)
        self.btn_parametres.clicked.connect(self.show_settings)

        self.btn_annexe6_retour.clicked.connect(self.show_main_menu)
        self.btn_browse_folder.clicked.connect(self.select_output_folder)
        self.btn_annexe6_lancer.clicked.connect(self.run_annexe6_from_ui)
        self.combo_georef.addItems(["", "Avec X C L F"])

        self.selected_line_layers = []
        self.btn_select_line_layers.clicked.connect(self.select_line_layers_dialog)
        self.btn_retour_creation_lot.clicked.connect(self.show_main_menu)
        self.btn_browse_output.clicked.connect(self.select_output_folder_lot)
        self.btn_browse_styles.clicked.connect(self.select_styles_folder)
        self.btn_lancer_creation_lot.clicked.connect(self.run_creation_lot)

        self.btn_browse_default_output.clicked.connect(self.select_default_output_folder)
        self.btn_browse_default_styles.clicked.connect(self.select_default_styles_folder)
        self.btn_save_settings.clicked.connect(self.save_settings)
        self.btn_param_retour.clicked.connect(self.show_main_menu)

        if self.combo_theme:
            self.combo_theme.currentTextChanged.connect(self.apply_theme)

        self.load_settings()

    # ─── Logs TaskManager ─────────────────────────────────────────────
    def _on_all_tasks_finished(self):
        QgsMessageLog.logMessage("[GestionnairePi] ► Toutes les tâches terminées", "GestionnairePi", Qgis.Info)

    # ─── MAJ combos selon pages ──────────────────────────────────────
    def _on_layers_changed(self, *args):
        page = self.stackedWidget.currentWidget()
        if page == self.page_annexe6:
            self.populate_layer_combos()
        elif page == self.page_creation_lot:
            self.populate_creation_lot_combos()

    # ─── Peuplement combos ───────────────────────────────────────────
    def populate_layer_combos(self):
        """
        Remplit les trois QComboBox (tronçons, zones, folios) et place
        automatiquement la sélection sur la première couche dont le nom
        *commence par* l’un des préfixes indiqués dans `defaults`.
        """
        # 0. Nettoyage
        self.combo_troncons.clear()
        self.combo_zones.clear()
        self.combo_folios.clear()

        # 1. Remplissage
        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer):
                continue

            geom = QgsWkbTypes.geometryType(lyr.wkbType())
            if geom == QgsWkbTypes.LineGeometry:
                self.combo_troncons.addItem(lyr.name())
            elif geom == QgsWkbTypes.PolygonGeometry:
                self.combo_zones.addItem(lyr.name())
                self.combo_folios.addItem(lyr.name())

        # 2. Préfixes à détecter en priorité
        defaults = {
            "troncons": ["lineaires"],        # préfixes souhaités (minuscules ou pas)
            "zones":    ["Zone_detection"],
            "folios":   ["Folios"],
        }

        def _select(combo: QtWidgets.QComboBox, prefixes: list[str]):
            """
            Sélectionne la première entrée dont le texte commence par l’un
            des préfixes donnés ; sinon, si la combo n’est pas vide, on
            choisit l’index 0.
            """
            for pfx in prefixes:
                # Qt.MatchStartsWith → « commence par »
                # (la recherche est sensible à la casse par défaut ; enlevez
                #  Qt.MatchCaseSensitive si vous préférez l’ignorer)
                idx = combo.findText(pfx, Qt.MatchStartsWith | Qt.MatchCaseSensitive)
                if idx != -1:
                    combo.setCurrentIndex(idx)
                    return
            if combo.count():
                combo.setCurrentIndex(0)

        _select(self.combo_troncons, defaults["troncons"])
        _select(self.combo_zones,    defaults["zones"])
        _select(self.combo_folios,   defaults["folios"])

    def populate_creation_lot_combos(self):
        self.combo_emprises.clear()
        self.combo_lineaires_me.clear()
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                geom = QgsWkbTypes.geometryType(lyr.wkbType())
                if geom == QgsWkbTypes.PolygonGeometry:
                    self.combo_emprises.addItem(lyr.name())
                elif geom == QgsWkbTypes.LineGeometry:
                    self.combo_lineaires_me.addItem(lyr.name())

    # ─── Navigation UI ───────────────────────────────────────────────
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

    # ─── Sélecteurs simples ─────────────────────────────────────────
    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if folder:
            self.line_output_folder.setText(folder)

    def select_output_folder_lot(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if folder:
            self.line_output.setText(folder)

    # ─── ANNEXE 6 ────────────────────────────────────────────────────
    def run_annexe6_from_ui(self):
        from gestionnaire_pi.core.annexe6.controller import Annexe6Processor
        Annexe6Processor(self.plugin.iface).run_custom(
            self.combo_troncons.currentText(),
            self.combo_zones.currentText(),
            self.combo_folios.currentText(),
            self.line_output_folder.text(),
        )

    # ─── CRÉATION LOT P.I. ───────────────────────────────────────────
    def run_creation_lot(self):
        # Validation minimale
        missing = []
        codes = [c.strip() for c in self.line_insee.text().split(";") if c.strip()]
        for c in codes:
            if not (c.isdigit() and len(c) == 5):
                missing.append(f"Code INSEE invalide : « {c} »")
        if not self._layer_by_name(self.combo_emprises.currentText()):
            missing.append("couche d’emprises")
        if not self.selected_line_layers:
            missing.append("couche(s) linéaire(s)")
        if not self._layer_by_name(self.combo_lineaires_me.currentText()):
            missing.append("couche de linéaires ME")

        if missing:
            QMessageBox.warning(self, "Champs manquants", ", ".join(missing))
            return

        self._show_progress_dialog()
        QTimer.singleShot(0, self._start_processing_task)

    def _cleanup_outputs(self, output_dir: str):
        """Supprime les fichiers de sortie qui pourraient bloquer l’algorithme."""
        if not output_dir:
            return
        targets = [
            os.path.join(output_dir, "export_folios.csv"),
            # os.path.join(output_dir, "lineaires.gpkg"),  # exemples possibles
            # os.path.join(output_dir, "folios.gpkg"),      # à adapter si besoin
        ]
        for path in targets:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                QgsMessageLog.logMessage(f"[GestionnairePi] Impossible de supprimer {path}: {e}", "GestionnairePi", Qgis.Warning)

    # ─── Lancement de la tâche Processing ────────────────────────────
    def _start_processing_task(self):
        self._task_start_time = time.time()

        params = {
            "insee": self.line_insee.text(),
            "emprises": self._layer_by_name(self.combo_emprises.currentText()),
            "lineaires": self.selected_line_layers,
            "lineaires_me": self._layer_by_name(self.combo_lineaires_me.currentText()),
            "inclure_classe_b": self.inclure_classe_b.isChecked(),
            "georeferencement": self.combo_georef.currentIndex(),
            "dossier_sortie": self.line_output.text(),
            "dossier_styles": self.line_styles.text(),
        }

        alg_id = "gestionnaire_pi_models:Principale"
        alg = QgsApplication.processingRegistry().algorithmById(alg_id)
        if alg is None:
            self._close_progress_dialog()
            QMessageBox.critical(self, "Erreur", f"Algorithme introuvable : {alg_id}")
            return

        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        feedback = TimingFeedback()          

        task = QgsProcessingAlgRunnerTask(alg, params, context, feedback)
        self.current_task, self.current_context = task, context
        task.progressChanged.connect(self.progress_line.set_progress)

        # 4) Callback exécuté sur le thread principal
        def _on_executed(success: bool, results: dict[str, object]):
            self._close_progress_dialog()
            if not success:
                QMessageBox.critical(self, "Erreur", feedback.text() or "Échec du traitement.")
                return

            proj         = QgsProject.instance()
            child        = results.get("CHILD_RESULTS", {})
            loaded       = 0

            # ───────── 1.  couches vecteur finales (déjà stylées) ─────────

            def _style_for(fname: str, styles_dir: str) -> str | None:
                """Associe un QML en fonction du nom de fichier."""
                fname = fname.lower()
                if "lineaires" in fname:
                    return os.path.join(styles_dir, "Lineaire.qml")
                if "folios" in fname:
                    return os.path.join(styles_dir, "Folios.qml")
                if "zone_detection" in fname:
                    return os.path.join(styles_dir, "Zone_detection.qml")
                return None


            # --- 1. mapping « style » → « savefeatures » -------------------------
            outputs = { # ordonné selon l'ordre du premier au dernier chargé
                'lin': child['native:savefeatures_1']['OUTPUT'], 
                'fol': child['native:savefeatures_2']['OUTPUT'],
                'zon': child['native:savefeatures_3']['OUTPUT'],
            }
            style_dir = params["dossier_styles"]

            for k, gpkg in outputs.items():

                # 1. Chemin du .qml – d’abord
                qml = os.path.join(
                    style_dir,
                    "Lineaire.qml"        if k == "lin" else
                    "Folios.qml"          if k == "fol" else
                    "Zone_detection.qml"  # k == "zon"
                )

                # 2. Ouverture du GeoPackage
                name   = os.path.splitext(os.path.basename(gpkg))[0]   # joli nom dans la Légende
                vlayer = QgsVectorLayer(gpkg, name, "ogr")
                if not vlayer.isValid():
                    QgsMessageLog.logMessage(f"⚠️ Impossible d’ouvrir {gpkg}", "GestionnairePi", Qgis.Warning)
                    continue

                # 3. Application + sauvegarde du style
                ok, _ = vlayer.loadNamedStyle(qml)
                if not ok:
                    QgsMessageLog.logMessage(f"⚠️ Style manquant : {qml}", "GestionnairePi", Qgis.Warning)
                else:
                    vlayer.saveStyleToDatabase('default', '', '', True)   # stocke le QML dans le gpkg

                # 4. Ajout au projet
                QgsProject.instance().addMapLayer(vlayer)
                loaded += 1

            # ───────── 2.  Ré-enregistrement du CSV (écrasement) ─────────
            csv_path = child.get("native:savefeatures_4", {}).get("FILE_PATH")
            if csv_path and os.path.exists(csv_path):
                try:
                    import csv, tempfile, shutil
                    # On ré-enregistre le fichier avec nos paramètres : UTF-8, délimiteur « ; », tout en texte
                    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
                    os.close(fd)

                    with open(csv_path, "r", encoding="utf-8", newline="") as src, \
                         open(tmp_path, "w", encoding="utf-8", newline="") as dst:
                        reader = csv.reader(src, delimiter=";")
                        writer = csv.writer(dst, delimiter=";", quoting=csv.QUOTE_NONE)
                        for row in reader:
                            writer.writerow(row)

                    # Remplace l'ancien fichier par la nouvelle version
                    shutil.move(tmp_path, csv_path)
                except Exception as e:
                    QgsMessageLog.logMessage(
                        f"[GestionnairePi] Ré-enregistrement CSV échoué : {e}",
                        "GestionnairePi", Qgis.Warning
                    )

            # ───────── 4.  message récapitulatif ─────────
            d = int(time.time() - self._task_start_time)

            # helper local pour formater la durée (> 1 h → « 1 h 05 min 12 s »)
            def _fmt(seconds: int) -> str:
                h, rem = divmod(seconds, 3600)
                m, s   = divmod(rem, 60)
                return f"{h} h {m:02d} min {s:02d} s" if h else f"{m:02d} min {s:02d} s"

            QMessageBox.information(
                self,
                "Succès",
                f"{loaded} couche(s) chargée(s).\n"
                f"Durée : {_fmt(d)}"
            )

        task.executed.connect(_on_executed)
        QgsApplication.taskManager().addTask(task)

    # ─── Progress dialog ─────────────────────────────────────────────
    def _show_progress_dialog(self):
        self.progress_dialog = QDialog(self)
        self.progress_dialog.setWindowTitle("Traitement en cours")
        self.progress_dialog.setWindowModality(Qt.ApplicationModal)
        self.progress_dialog.setWindowFlags(
            self.progress_dialog.windowFlags() | Qt.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self.progress_dialog)

        # — ligne de progression + WEBP animé —
        if random.random() < 0.01 : 
            tete = ":/plugins/gestionnaire_pi/resources/img/progress_2.webp"
        else :
            tete = ":/plugins/gestionnaire_pi/resources/img/progress_1.webp"
        self.progress_line = ProgressLineWebp(
            tete,
            self.progress_dialog,
        )
        self.progress_line.set_progress(0)           # départ à 0 %
        # layout.addWidget(self.progress_line, alignment=Qt.AlignCenter)
        layout.addWidget(self.progress_line)          

        label_text = QLabel(
            "Le traitement est en cours…\nVeuillez patienter.",
            self.progress_dialog,
        )
        label_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_text)

        self.progress_dialog.show()

    def _close_progress_dialog(self):
        if hasattr(self, "progress_dialog"):
            dlg = self.progress_dialog
            QMetaObject.invokeMethod(dlg, "close", Qt.QueuedConnection)
            QMetaObject.invokeMethod(dlg, "deleteLater", Qt.QueuedConnection)
            del self.progress_dialog

    # ─── Utilitaires ─────────────────────────────────────────────────
    def _layer_by_name(self, name: str | None) -> QgsVectorLayer | None:
        if not name:
            return None
        layers = QgsProject.instance().mapLayersByName(name)
        return layers[0] if layers else None

    # ─── PARAMÈTRES & THÈME ───────────────────────────────────────────

    def show_settings(self):
        self.stackedWidget.setCurrentWidget(self.page_parametres)

    def load_settings(self):
        self.line_default_output.setText(self.settings.get_output_folder())
        self.line_default_styles.setText(self.settings.get_styles_folder())
        self.check_logs.setChecked(self.settings.get_log_detail())
        self.current_color = self.settings.get_color()
        self.setStyleSheet(f"background-color: {self.current_color.name()};")
        if hasattr(self, "label_color"):
            self.label_color.setStyleSheet(
                f"background-color: {self.current_color.name()}"
            )
        if self.combo_theme:
            theme = self.settings.get_theme()
            idx = self.combo_theme.findText(theme)
            self.combo_theme.setCurrentIndex(idx if idx >= 0 else 0)
            self.apply_theme(theme)

    def save_settings(self):
        self.settings.set_output_folder(self.line_default_output.text())
        self.settings.set_styles_folder(self.line_default_styles.text())
        self.settings.set_log_detail(self.check_logs.isChecked())
        self.settings.set_color(self.current_color)
        if self.combo_theme:
            self.settings.set_theme(self.combo_theme.currentText())

    def select_default_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de sortie")
        if folder:
            self.line_default_output.setText(folder)

    def select_default_styles_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier des styles")
        if folder:
            self.line_default_styles.setText(folder)

    def select_styles_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier des styles")
        if folder:
            self.line_styles.setText(folder)

    def apply_theme(self, theme: str):
        """
        Applique le thème choisi à toute l’application.
        """
        styles = {
            # ────────────────────────── THÈME CLAIR ──────────────────────────
            "Thème clair": """
                /* --- widgets fixes -------------------------------------------------- */
                QDockWidget, QWidget     { background-color: #f0f0f0; color: #000; }
                QLineEdit, QComboBox,
                QTextEdit                { background-color: #fff;    color: #000;
                                            border: 1px solid #ccc; }
                QPushButton, QTreeWidget { background-color: #e0e0e0; color: #000; }
                QCheckBox                { color: #000; }

                QComboBox QListView {
                    background-color: #ffffff;
                    color: #000000;
                }
            """,

            # ───────────────────────── THÈME SOMBRE ─────────────────────────
            "Thème sombre": """
                QDockWidget, QWidget     { background-color: #2e2e2e; color: #ffffff; }
                QLineEdit, QComboBox,
                QTextEdit                { background-color: #3c3c3c; color: #ffffff;
                                            border: 1px solid #555555; }
                QPushButton, QTreeWidget { background-color: #444444; color: #ffffff; }
                QCheckBox                { color: #ffffff; }

                QComboBox QListView {
                    background-color: #333333;
                    color: #dddddd;
                }
            """,

            # ──────────────────────── THÈME RATON LAVEUR ────────────────────────
            "Thème raton laveur": """
                QWidget#page_main_menu, QWidget#page_creation_lot, QWidget#page_annexe6 , QWidget#page_creation_lot, QWidget#page_parametres {
                    background-color: #0051a2 ;
                    background-image: url(:/plugins/gestionnaire_pi/resources/img/racoon_256.png);
                    background-repeat: no-repeat ;
                    background-position: bottom center ;
                    background-size: cover ;
                }
                QDockWidget, QWidget     { background-color: #0051a2 ; color: #76b855; }
                QLineEdit, QComboBox, QTextEdit {background-color: #009dc5 ;color: #000 ; border: 1px solid #009dc5 ; }
                QPushButton {background-color: #009dc5;color: #0d0d0d ; }
                QTreeWidget {background-color: #ff0000;color: #00ff00 ; }
                QCheckBox {color: #76b855;}
                QComboBox QListView {background-color: #76b855 ; color: #0d0d0d;}
            """,
        }
        self.setStyleSheet(styles.get(theme, styles["Thème raton laveur"]))

    # ─── DIALOGUE DE SÉLECTION DES LINÉAIRES ──────────────────────────
    def select_line_layers_dialog(self):
        layers = [lyr for lyr in QgsProject.instance().mapLayers().values()
                  if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.LineGeometry]

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Sélectionner les linéaires")
        lay = QtWidgets.QVBoxLayout(dlg)

        cbs = []
        for lyr in layers:
            cb = QtWidgets.QCheckBox(lyr.name())
            cb.setChecked(lyr.name() in [l.name() for l in self.selected_line_layers])
            lay.addWidget(cb)
            cbs.append((cb, lyr))

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        lay.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        if dlg.exec_():
            self.selected_line_layers = [lyr for cb, lyr in cbs if cb.isChecked()]
            n = len(self.selected_line_layers)
            self.line_selected_layers.setText(f"{n} couche(s) sélectionnée(s)" if n else "Aucune couche sélectionnée")

    # ─── Fermeture ───────────────────────────────────────────────────
    def closeEvent(self, e):
        self.closingPlugin.emit()
        e.accept()