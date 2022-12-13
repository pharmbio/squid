# qt libraries
from qtpy.QtWidgets import QFrame, QDoubleSpinBox, QSpinBox, QGridLayout, QLabel

from control._def import *
from control.gui import *

from typing import Optional, Union, List, Tuple

NZ_LABEL='num images'
DZ_LABEL='delta Z (um)'
DZ_TOOLTIP="""use autofocus by taking z-stack of images (NZ images, with dz um distance between images), then
calculating a focus metric and choosing the image plane with the best metric.

the images are taken in the channel that is currently selected for live view (led+micro will be turned on if they are off)

this will take a few seconds"""

DEFAULT_NZ=10
DEFAULT_DELTAZ=1.524

class AutoFocusWidget(QFrame):
    @property
    def autofocusController(self):
        return self.hcs_controller.autofocusController
        
    def __init__(self, 
        hcs_controller,
        gui,
    ):
        super().__init__()

        self.hcs_controller=hcs_controller
        self.gui=gui

        self.entry_delta = SpinBoxDouble(minimum=0.0,maximum=20.0,step=0.2,num_decimals=3,default=DEFAULT_DELTAZ,keyboard_tracking=False,on_valueChanged=self.set_deltaZ).widget

        self.entry_N = SpinBoxInteger(minimum=3,maximum=20,step=1,default=DEFAULT_NZ,keyboard_tracking=False,on_valueChanged=self.autofocusController.set_N).widget

        self.btn_autofocus = Button('Run Software Autofocus',default=False,checkable=True,checked=False,tooltip=DZ_TOOLTIP,on_clicked=self.autofocus_start).widget

        # layout
        qtlabel_dz=Label(DZ_LABEL,tooltip=DZ_TOOLTIP).widget
        qtlabel_Nz=Label(NZ_LABEL,tooltip=DZ_TOOLTIP).widget
        
        self.grid = Grid(
            [ qtlabel_dz, self.entry_delta, qtlabel_Nz, self.entry_N, self.btn_autofocus ]
        ).layout
        self.setLayout(self.grid)

        self.autofocusController.set_N(DEFAULT_NZ)
        self.set_deltaZ(DEFAULT_DELTAZ)

    def set_deltaZ(self,value):
        mm_per_ustep = MACHINE_CONFIG.SCREW_PITCH_Z_MM/(self.autofocusController.navigationController.z_microstepping*MACHINE_CONFIG.FULLSTEPS_PER_REV_Z)
        deltaZ = round(value/1000/mm_per_ustep)*mm_per_ustep*1000
        #self.entry_delta.setValue(deltaZ) # overwrite selected value with more precise valid value
        self.autofocusController.set_deltaZ(deltaZ)

    def autofocus_start(self,_btn_state):
        self.gui.set_all_interactibles_enabled(False)
        self.autofocusController.autofocusFinished.connect(self.autofocus_is_finished)

        self.autofocusController.autofocus()

    def autofocus_is_finished(self):
        self.autofocusController.autofocusFinished.disconnect(self.autofocus_is_finished)
        self.btn_autofocus.setChecked(False)
        self.gui.set_all_interactibles_enabled(True)
