# -*- coding: utf-8 -*-
"""
/*************************
 gestionnaire_pi
*************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from .resources import *
from .gestionnaire_pi_dockwidget import GestionnairePiDockWidget
from .annexe6_runner import run_annexe6
from .modeler_runner import run_creation_lot
import os.path


class GestionnairePi:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        locale = str(QSettings().value('locale/userLocale'))[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'GestionnairePi_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&Gestionnaire PI')
        self.toolbar = self.iface.addToolBar(u'GestionnairePi')
        self.toolbar.setObjectName(u'GestionnairePi')

        self.pluginIsActive = False
        self.dockwidget = None

    def tr(self, message):
        return QCoreApplication.translate('GestionnairePi', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True,
                   status_tip=None, whats_this=None, parent=None):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = ':/plugins/gestionnaire_pi/icon.png'

        self.add_action(
            icon_path,
            text=self.tr(u'Ouvrir le tableau de bord'),
            callback=self.run,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True)

        self.add_action(
            icon_path,
            text=self.tr(u'Création lot P.I'),
            callback=self.run_creation_lot,
            parent=self.iface.mainWindow(),
            add_to_menu=True,
            add_to_toolbar=False)

        self.add_action(
            icon_path,
            text=self.tr(u'Génération Annexe 6'),
            callback=self.run_annexe_6,
            parent=self.iface.mainWindow(),
            add_to_menu=True,
            add_to_toolbar=False)

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False
        self.dockwidget = None  # ← important pour pouvoir le recréer plus tard

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        if not self.pluginIsActive:
            self.pluginIsActive = True
            if self.dockwidget is None:
                self.dockwidget = GestionnairePiDockWidget(self)
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

    def run_creation_lot(self):
        run_creation_lot(self.iface)

    def run_annexe_6(self):
        run_annexe6(self.iface)
    
    def show_settings(self):
        self.dockwidget.stackedWidget.setCurrentWidget(self.dockwidget.page_parametres)