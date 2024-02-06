# qt libraries
from qtpy.QtCore import QObject, QThread, Signal # type: ignore
from qtpy.QtWidgets import QApplication

import control.utils as utils
from control._def import *

import time
import numpy as np

from typing import Optional, List, Union, Tuple

from control.camera import Camera
from control.core import NavigationController, LiveController
from control.microcontroller import Microcontroller

class AutofocusWorker(QObject):

    finished = Signal()
    image_to_display = Signal(np.ndarray)

    def __init__(self,autofocusController:"AutoFocusController"):
        QObject.__init__(self)
        self.autofocusController = autofocusController

        self.camera:Camera = self.autofocusController.camera
        self.microcontroller:Microcontroller = self.autofocusController.navigation.microcontroller
        self.navigation = self.autofocusController.navigation
        self.liveController = self.autofocusController.liveController

        self.N = self.autofocusController.N
        self.deltaZ_usteps = self.autofocusController.deltaZ_usteps
        
        self.crop_width = self.autofocusController.crop_width
        self.crop_height = self.autofocusController.crop_height

    def run(self):
        self.run_autofocus(self.autofocusController.focus_config)
        self.finished.emit()

    def run_autofocus(self,config):
        # @@@ to add: increase gain, decrease exposure time
        # @@@ can move the execution into a thread - done 08/21/2021
        focus_measure_vs_z:List[float] = [0]*self.N
        focus_measure_max:float = 0

        z_af_offset_usteps = self.deltaZ_usteps*round(self.N/2)

        # maneuver for achiving uniform step size and repeatability when using open-loop control
        # can be moved to the firmware
        self.navigation.move_z_usteps(- self.microcontroller.clear_z_backlash_usteps - z_af_offset_usteps, wait_for_completion={})
        self.navigation.move_z_usteps(  self.microcontroller.clear_z_backlash_usteps                     , wait_for_completion={})

        with self.camera.wrapper.ensure_streaming():
            steps_moved = 0
            for i in range(self.N):
                self.navigation.move_z_usteps(self.deltaZ_usteps,wait_for_completion={})
                steps_moved = steps_moved + 1

                image=self.liveController.snap(config)

                self.image_to_display.emit(image)
                QApplication.processEvents()

                focus_measure = utils.calculate_focus_measure(image,MACHINE_CONFIG.MUTABLE_STATE.FOCUS_MEASURE_OPERATOR)
                focus_measure_vs_z[i] = focus_measure
                focus_measure_max = max(focus_measure, focus_measure_max)
                if focus_measure < focus_measure_max*MACHINE_CONFIG.AF.STOP_THRESHOLD:
                    break

            # determine the in-focus position
            idx_in_focus = focus_measure_vs_z.index(max(focus_measure_vs_z))

            # maneuver for achiving uniform step size and repeatability when using open-loop control
            _usteps_to_clear_backlash=self.microcontroller.clear_z_backlash_usteps
            self.navigation.move_z_usteps(-_usteps_to_clear_backlash-steps_moved*self.deltaZ_usteps,wait_for_completion={})
            self.navigation.move_z_usteps(_usteps_to_clear_backlash+(idx_in_focus+1)*self.deltaZ_usteps,wait_for_completion={})

            # take focused image and display
            image=self.liveController.snap(config)

            self.image_to_display.emit(image)
            QApplication.processEvents()

            # display warning in certain cases
            if idx_in_focus == 0:
                MAIN_LOG.log('warning - moved to the bottom end of the Autofocus range (this is not good)')
            elif idx_in_focus == self.N-1:
                MAIN_LOG.log('warning - moved to the top end of the Autofocus range (this is not good)')

class AutoFocusController(QObject):
    """
    runs autofocus procedure on request\n
    can be configured between creation and request
    """

    z_pos = Signal(float)
    autofocusFinished = Signal()
    image_to_display = Signal(np.ndarray)

    def __init__(self,camera:Camera,navigationController:NavigationController,liveController:LiveController):
        QObject.__init__(self)
        self.camera = camera
        self.navigation = navigationController
        self.liveController = liveController
        self.N:int = 1 # arbitrary value of type
        self.deltaZ_mm:float = 0.1 # arbitrary value of type
        self.crop_width:int = MACHINE_CONFIG.AF.CROP_WIDTH
        self.crop_height:int = MACHINE_CONFIG.AF.CROP_HEIGHT
        self.autofocus_in_progress:bool = False
        self.thread:Optional[QThread] = None

    @property
    def deltaZ_usteps(self)->int:
        return self.navigation.microcontroller.mm_to_ustep_z(self.deltaZ_mm)

    def set_crop(self,crop_width:int,crop_height:int):
        self.crop_width = crop_width
        self.crop_height = crop_height

    def autofocus(self,
        config,
        N:int,
        dz_mm:float,
    ):
        # create a QThread object
        if not self.thread is None and self.thread.isRunning():
            MAIN_LOG.log('*** autofocus thread is still running ***')
            self.thread.terminate()
            self.thread.wait()
            MAIN_LOG.log('*** autofocus thread manually stopped ***')

        self.N=N
        self.deltaZ_mm=dz_mm

        self.focus_config=config

        self.thread = QThread()
        # create a worker object
        self.autofocusWorker = AutofocusWorker(self)
        # move the worker to the thread
        self.autofocusWorker.moveToThread(self.thread)
        # connect signals and slots
        self.thread.started.connect(self.autofocusWorker.run)
        self.autofocusWorker.finished.connect(self._on_autofocus_completed)
        self.autofocusWorker.finished.connect(self.autofocusWorker.deleteLater)
        self.autofocusWorker.finished.connect(self.thread.quit)
        self.autofocusWorker.image_to_display.connect(self.slot_image_to_display)
        # self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.thread.quit)
        # start the thread
        self.thread.start()
        
    def _on_autofocus_completed(self):

        # emit the autofocus finished signal to enable the UI
        self.autofocusFinished.emit()

        # update the state
        self.autofocus_in_progress = False

    def slot_image_to_display(self,image):
        self.image_to_display.emit(image)

    def wait_till_autofocus_has_completed(self):
        while self.autofocus_in_progress == True:
            time.sleep(0.005)

