# -*- coding: utf-8 -*-
"""
/*************************
 gestionnaire_pi
*************************/
"""
import os
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import (
    QgsApplication,
    QgsProcessingProvider,
    QgsProcessingModelAlgorithm
)
from .resources import *
from gestionnaire_pi.ui.main_dockwidget import GestionnairePiDockWidget

class Model3Provider(QgsProcessingProvider):
    """Provider qui expose tous les .model3 du dossier models/ comme algorithmes Processing."""
    def __init__(self, models_folder, parent=None):
        super().__init__(parent)
        self.models_folder = models_folder

    def id(self):
        return 'gestionnaire_pi_models'

    def name(self):
        return 'Gestionnaire PI Models'

    def longName(self):
        return self.name()

    def loadAlgorithms(self):
        # pour chaque .model3, on crée un QgsProcessingModelAlgorithm et on l'ajoute
        for fname in os.listdir(self.models_folder):
            if fname.lower().endswith('.model3'):
                model_path = os.path.join(self.models_folder, fname)
                alg = QgsProcessingModelAlgorithm()
                if alg.fromFile(model_path):
                    self.addAlgorithm(alg)

class GestionnairePi:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.model_provider = None
        
        # Chargement des traductions
        locale = str(QSettings().value('locale/userLocale'))[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            f'GestionnairePi_{locale}.qm'
        )
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Barre d'outils et menu
        self.actions = []
        self.menu = self.tr('&Gestionnaire PI')
        self.toolbar = self.iface.addToolBar('GestionnairePi')
        self.toolbar.setObjectName('GestionnairePi')

        # État du plugin
        self.pluginIsActive = False
        self.dockwidget = None

    def tr(self, message):
        return QCoreApplication.translate('GestionnairePi', message)

    def add_action(self, icon_path, text, callback,
                   enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True,
                   status_tip=None, whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip:
            action.setStatusTip(status_tip)
        if whats_this:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            self.toolbar.addAction(action)
        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        # 1) Votre bouton “Ouvrir le tableau de bord”
        icon_path = ':/plugins/gestionnaire_pi/icon.png'
        self.add_action(
            icon_path,
            text=self.tr('Ouvrir le tableau de bord'),
            callback=self.run,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True
        )

        # 2) Enregistrement du fournisseur de modèles
        models_folder = os.path.join(self.plugin_dir, 'models')
        self.model_provider = Model3Provider(models_folder)
        QgsApplication.processingRegistry().addProvider(self.model_provider)

    def unload(self):
        # suppression des actions et de la barre
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        # désenregistrement du provider
        if self.model_provider:
            QgsApplication.processingRegistry().removeProvider(self.model_provider)
            self.model_provider = None

        # fermeture du dockwidget
        if self.dockwidget:
            self.dockwidget.close()
            self.dockwidget = None
        del self.toolbar

    def run(self):
        # Ouverture du dockwidget
        if not self.pluginIsActive:
            self.pluginIsActive = True
            if self.dockwidget is None:
                self.dockwidget = GestionnairePiDockWidget(self)
                self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

    def onClosePlugin(self):
        # Fermeture du plugin
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False
        self.dockwidget = None
