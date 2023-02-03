# qt libraries
from qtpy.QtWidgets import QFrame, QDoubleSpinBox, QSpinBox, QGridLayout, QLabel

from control._def import *
from control.gui import *

from .laser_autofocus import LaserAutofocusControlWidget

from typing import Optional, Union, List, Tuple

NZ_LABEL='num images'
DZ_LABEL='delta Z (um)'
DZ_TOOLTIP="""use autofocus by taking z-stack of images (NZ images, with dz um distance between images), then
calculating a focus metric and choosing the image plane with the best metric.

the images are taken in the channel that is currently selected for live view (led+micro will be turned on if they are off)

this will take a few seconds"""

DEFAULT_NZ=10
DEFAULT_DELTAZ=1.5

class SoftwareAutoFocusWidget(QFrame):
    def __init__(self,
        software_af_controller,
        configuration_manager,
        on_set_all_callbacks_enabled:Callable[[bool,],None]
    ):
        super().__init__()

        self.software_af_controller=software_af_controller
        self.configuration_manager=configuration_manager
        self.on_set_all_callbacks_enabled=on_set_all_callbacks_enabled

        self.entry_delta = SpinBoxDouble(minimum=0.1,maximum=20.0,step=0.1,num_decimals=3,default=DEFAULT_DELTAZ,keyboard_tracking=False).widget
        self.entry_N = SpinBoxInteger(minimum=3,maximum=23,step=2,default=DEFAULT_NZ,keyboard_tracking=False).widget

        self.btn_autofocus = Button("Run",default=False,checkable=True,checked=False,tooltip=DZ_TOOLTIP,on_clicked=self.autofocus_start).widget

        self.channel_dropdown=Dropdown(
            items=[config.name for config in self.configuration_manager.configurations],
            current_index=0,
        ).widget

        # layout
        qtlabel_dz=Label(DZ_LABEL,tooltip=DZ_TOOLTIP).widget
        qtlabel_Nz=Label(NZ_LABEL,tooltip=DZ_TOOLTIP).widget
        
        self.grid = Grid(
            [ qtlabel_dz, self.entry_delta, qtlabel_Nz, self.entry_N, self.channel_dropdown, self.btn_autofocus ]
        ).layout
        self.setLayout(self.grid)

    def autofocus_start(self,_btn_state):
        self.on_set_all_callbacks_enabled(False)
        self.software_af_controller.autofocusFinished.connect(self.autofocus_is_finished)

        self.software_af_controller.autofocus(
            self.configuration_manager.configurations[self.channel_dropdown.currentIndex()],
            N=self.entry_N.value(),
            dz=self.entry_delta.value(),
        )

    def autofocus_is_finished(self):
        self.software_af_controller.autofocusFinished.disconnect(self.autofocus_is_finished)
        self.btn_autofocus.setChecked(False)
        self.on_set_all_callbacks_enabled(True)

class AutofocusWidget:
    software_af_debug_display:Optional[QWidget]
    software_af_control:QWidget

    laser_af_debug_display:Optional[QWidget]
    laser_af_control:QWidget

    af_control:QWidget

    def __init__(self,
        laser_af_controller,
        software_af_controller,
        get_current_z_pos_in_mm,
        on_set_all_callbacks_enabled,
        configuration_manager,
        debug_laser_af:bool=False,
        debug_software_af:bool=False,
    ):
        if debug_software_af:
            self.software_af_debug_display=BlankWidget(background_color="black")
        else:
            self.software_af_debug_display=None

        self.software_af_control=SoftwareAutoFocusWidget(
            software_af_controller = software_af_controller,
            on_set_all_callbacks_enabled = on_set_all_callbacks_enabled,
            configuration_manager = configuration_manager
        )

        if debug_laser_af:
            self.laser_af_debug_display=BlankWidget(background_color="red")
        else:
            self.laser_af_debug_display=None

        self.laser_af_control=LaserAutofocusControlWidget(laser_af_controller,get_current_z_pos_in_mm=get_current_z_pos_in_mm)

        self.af_control=VBox(
            Dock(self.laser_af_control,"Laser AF"),
            Dock(self.software_af_control,"Software Af"),
        ).widget

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.laser_af_control,
            self.software_af_control,
        ]
    
