from qgis.PyQt.QtWidgets import QMessageBox
from .annexe6_main import Annexe6Processor
"""
/*************************
 annexe6_runner
*************************/
"""
def run_annexe6(iface):
    try:
        processor = Annexe6Processor(iface)
        processor.run()
    except Exception as e:
        QMessageBox.critical(None, "Erreur", f"Une erreur est survenue : {str(e)}")
