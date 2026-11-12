"""Background computation only receives detached Python data."""
import weakref
from qgis.PyQt import sip
from qgis.core import QgsTask
from .gtfs_adapter import calculate

class OccupancyTask(QgsTask):
    def __init__(self,panel,token,data,config):
        super().__init__('MIC_GTFS: conflitti fermata',QgsTask.CanCancel)
        self.panel=weakref.ref(panel);self.token=token;self.data=data;self.config=config;self.result=None;self.failure=None
    def run(self):
        try:
            self.result=calculate(self.data,self.config,self.isCanceled);self.setProgress(100);return not self.isCanceled()
        except Exception as error:self.failure=str(error);return False
    def finished(self,success):
        panel=self.panel()
        if panel is not None and not sip.isdeleted(panel):panel.task_finished(self.token,success,self.result,self.failure,self.isCanceled())
        self.data=None
