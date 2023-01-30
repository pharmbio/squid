# qt libraries
from qtpy.QtCore import Signal, Qt # type: ignore
from qtpy.QtWidgets import QFrame, QComboBox, QDoubleSpinBox, QPushButton, QSlider, QGridLayout, QLabel, QVBoxLayout, QFileDialog, QApplication

import time

from control._def import *
from control.core import Configuration, LiveController, ConfigurationManager, StreamingCamera

from control.typechecker import TypecheckFunction
from control.gui import *

from typing import Optional, Union, List, Tuple, Callable

import numpy

# 'Live' button text
LIVE_BUTTON_IDLE_TEXT="Start Live"
LIVE_BUTTON_RUNNING_TEXT="Stop Live"

LIVE_BUTTON_TOOLTIP="""start/stop live image view

displays each image that is recorded by the camera

useful for manual investigation of a plate and/or imaging settings. Note that this can lead to strong photobleaching. Consider using the snapshot button instead (labelled 'snap')"""

CAMERA_PIXEL_FORMAT_TOOLTIP="camera pixel format\n\nMONO8 means monochrome (grey-scale) 8bit\nMONO12 means monochrome 12bit\n\nmore bits can capture more detail (8bit can capture 2^8 intensity values, 12bit can capture 2^12), but also increase file size"

class LiveControlWidget(QFrame):
    signal_newExposureTime = Signal(float)
    signal_newAnalogGain = Signal(float)

    @property
    def fps_trigger(self)->float:
        return self.liveController.fps_trigger

    def __init__(self,
        liveController:LiveController,
        configurationManager:ConfigurationManager,
        on_new_frame:Callable[[numpy.ndarray,],None]
    ):
        super().__init__()
        self.liveController = liveController
        self.configurationManager = configurationManager
        self.on_new_frame=on_new_frame
        
        self.triggerMode = TriggerMode.SOFTWARE
        # note that this references the object in self.configurationManager.configurations
        self.currentConfiguration:Configuration = self.configurationManager.configurations[0]

        self.add_components()
        self.liveController.set_microscope_mode(self.currentConfiguration)

        self.is_switching_mode = False # flag used to prevent from settings being set by twice - from both mode change slot and value change slot; another way is to use blockSignals(True)

        self.stop_requested=False

    def add_components(self):
        self.entry_triggerFPS = SpinBoxDouble(minimum=0.02,maximum=100.0,step=1.0,default=self.fps_trigger,
            on_valueChanged=self.liveController.set_trigger_fps
        ).widget

        self.btn_live=Button(LIVE_BUTTON_IDLE_TEXT,checkable=True,checked=False,default=False,tooltip=LIVE_BUTTON_TOOLTIP,on_clicked=self.toggle_live).widget

        self.camera_pixel_format_widget=Dropdown(
            items=self.liveController.camera.wrapper.pixel_formats,
            current_index=0, # default pixel format is 8 bits
            tooltip=CAMERA_PIXEL_FORMAT_TOOLTIP,
            on_currentIndexChanged=lambda index:self.liveController.camera.set_pixel_format(self.liveController.camera.wrapper.pixel_formats[index])
        ).widget

        self.grid = VBox(
            Grid([ # general camera settings
                Label('pixel format',tooltip=CAMERA_PIXEL_FORMAT_TOOLTIP).widget, 
                self.camera_pixel_format_widget,
            ]).layout,
            Grid([ # start live imaging
                self.btn_live,
                Label('FPS',tooltip="take this many images per second.\n\nNote that the FPS is practially capped by the exposure time. A warning message will be printed in the terminal if the actual number of images per second does not match the requested number.").widget,
                self.entry_triggerFPS,
            ]).layout,
        ).layout
        self.grid.addStretch()
        self.setLayout(self.grid)

    @TypecheckFunction
    def toggle_live(self,pressed:bool):
        if pressed:
            self.stop_requested=False

            self.btn_live.setText(LIVE_BUTTON_RUNNING_TEXT)
            QApplication.processEvents()

            max_fps=self.liveController.fps_trigger

            self.emit_camera_settings()

            with StreamingCamera(self.liveController.camera):
                last_image_time=time.monotonic()
                while not self.stop_requested:
                    current_time=time.monotonic()
                    time_to_next_image=1/max_fps - (current_time-last_image_time)
                    if time_to_next_image>0:
                        time.sleep(time_to_next_image)
                        QApplication.processEvents()

                    new_image=self.liveController.snap(config=self.currentConfiguration)
                    self.on_new_frame(new_image)
                    last_image_time=current_time

            self.btn_live.setText(LIVE_BUTTON_IDLE_TEXT)
            QApplication.processEvents()
        else:
            self.stop_requested=True

    @TypecheckFunction
    def emit_camera_settings(self):
        self.signal_newAnalogGain.emit(self.configurationManager.configurations[0].analog_gain)
        self.signal_newExposureTime.emit(self.configurationManager.configurations[0].exposure_time)
