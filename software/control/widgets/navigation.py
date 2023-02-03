# qt libraries
from qtpy.QtWidgets import QFrame, QLabel, QDoubleSpinBox, QGridLayout, QMessageBox, QVBoxLayout, QApplication

from control._def import *
from control.gui import *
from control.core import Core

from typing import Optional, Union, List, Tuple

BTN_LOADING_POSITION_IDLE_UNLOADED="go to loading position"
BTN_LOADING_POSITION_IDLE_LOADED="leave loading position"
BTN_LOADING_POSITION_RUNNING="moving..."
BTN_ZERO_Z_LABEL="Zero Z"
BTN_ZERO_Z_TOOLTIP="""
Display offset Z position.

The current position will be set as the new zero, and the position will then be displayed relative to this new zero.
This is for display purposes only, it has not influence on the function of the software or the microscope.

Clicking this button again will restore the original (real) zero.

This is useful e.g. to determine a channel specific offset.
"""
POS_X_LABEL="X (mm)"
POS_X_TOOLTIP="Position of the stage in X (in mm, relative to top left corner of well A1)"
POS_Y_LABEL="Y (mm)"
POS_Y_TOOLTIP="Position of the stage in Y (in mm, relative to top left corner of well A1)"
POS_Z_LABEL="Z (um)"
POS_Z_TOOLTIP="Position of the objective in Z (in mm, relative to the lowest possible position of the objective)"

class NavigationWidget(QFrame):
    @property
    def navigationController(self):
        return self.core.navigation

    def __init__(self, 
        core:Core,
        on_loading_position_toggle:Callable[[bool,],None],
    ):
        super().__init__()

        self.core=core
        self.on_loading_position_toggle=on_loading_position_toggle

        self.label_Xpos = Label("0,0",text_selectable=True,tooltip=POS_X_TOOLTIP).widget
        self.label_Xpos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dX = SpinBoxDouble(minimum=0.0,maximum=25.0,step=0.2,default=1.0,num_decimals=3,keyboard_tracking=False).widget
        self.btn_moveX_forward = Button('Forward',tooltip="Move forward (away from zero) in X by distance specified in the field on the left.",on_clicked=self.move_x_forward).widget
        self.btn_moveX_backward = Button('Backward',tooltip="Move backward (towards zero) in X by distance specified in the field on the left.",on_clicked=self.move_x_backward).widget
        self.real_pos_x:float=0.0 # real x position of objective/slide in mm
        
        self.label_Ypos = Label("0,0",text_selectable=True,tooltip=POS_Y_TOOLTIP).widget
        self.label_Ypos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dY = SpinBoxDouble(minimum=0.0,maximum=25.0,step=0.2,default=1.0,num_decimals=3,keyboard_tracking=False).widget
        self.btn_moveY_forward = Button('Forward',tooltip="Move forward (away from zero) in Y by distance specified in the field on the left.",on_clicked=self.move_y_forward).widget
        self.btn_moveY_backward = Button('Backward',tooltip="Move backward (towards zero) in Y by distance specified in the field on the left.",on_clicked=self.move_y_backward).widget
        self.real_pos_y:float=0.0 # real y position of objective/slide in mm

        self.label_Zpos = Label("0,0",text_selectable=True,tooltip=POS_Z_TOOLTIP).widget
        self.label_Zpos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dZ = SpinBoxDouble(minimum=0.0,maximum=1000.0,step=0.2,default=10.0,num_decimals=3,keyboard_tracking=False).widget
        self.btn_moveZ_forward = Button('Forward',tooltip="Move forward (away from zero) in Z by distance specified in the field on the left.",on_clicked=self.move_z_forward).widget
        self.btn_moveZ_backward = Button('Backward',tooltip="Move backward (towards zero) in Z by distance specified in the field on the left.",on_clicked=self.move_z_backward).widget
        self.real_pos_z:float=0.0 # real z position of objective/slide in mm

        self.btn_zero_Z = Button(BTN_ZERO_Z_LABEL,tooltip=BTN_ZERO_Z_TOOLTIP,checkable=True,on_clicked=self.zero_z).widget
        self.zero_z_offset=0.0

        self.btn_goToLoadingPosition=Button(BTN_LOADING_POSITION_IDLE_UNLOADED,tooltip="Enter/Leave stage loading position, so that a plate can be easily taken off/put on the stage.",checkable=True).widget
        self.btn_goToLoadingPosition.clicked.connect(self.loading_position_toggle)
        
        if MACHINE_CONFIG.DISPLAY.SHOW_XY_MOVEMENT:
            grid_line0 = Grid([ Label(POS_X_LABEL,tooltip=POS_X_TOOLTIP).widget, self.label_Xpos, self.entry_dX, self.btn_moveX_forward, self.btn_moveX_backward, ]).layout
            grid_line1 = Grid([ Label(POS_Y_LABEL,tooltip=POS_Y_TOOLTIP).widget, self.label_Ypos, self.entry_dY, self.btn_moveY_forward, self.btn_moveY_backward, ]).layout

        grid_line2 = Grid([ Label(POS_Z_LABEL,tooltip=POS_Z_TOOLTIP).widget, self.label_Zpos, self.entry_dZ, self.btn_moveZ_forward, self.btn_moveZ_backward, ]).layout
        grid_line3 = Grid([ self.btn_zero_Z, self.btn_goToLoadingPosition ]).layout

        grid_lines=[]
        if MACHINE_CONFIG.DISPLAY.SHOW_XY_MOVEMENT:
            grid_lines.extend([
                [grid_line0],
                [grid_line1],
            ])
        grid_lines.extend([
            [grid_line2],
            [grid_line3],
        ])
        self.setLayout(Grid(*grid_lines).layout)

        self.core.navigation.xPos.connect(self.set_pos_x)
        self.core.navigation.yPos.connect(self.set_pos_y)
        self.core.navigation.zPos.connect(self.set_pos_z)

    def loading_position_toggle(self,entered:bool):
        """
        toggle loading position (or at least call callback that is supposed to do this)
        the button is disabled while the callback is called (i.e. disabled before call, and enabled after callback has finished)
        """
        if entered:
            self.btn_goToLoadingPosition.setText(BTN_LOADING_POSITION_RUNNING)
            self.btn_goToLoadingPosition.setDisabled(True)

            self.on_loading_position_toggle(True)

            self.btn_goToLoadingPosition.setEnabled(True)
            self.btn_goToLoadingPosition.setText(BTN_LOADING_POSITION_IDLE_LOADED)
        else:
            self.btn_goToLoadingPosition.setText(BTN_LOADING_POSITION_RUNNING)
            self.btn_goToLoadingPosition.setDisabled(True)

            self.on_loading_position_toggle(False)

            self.btn_goToLoadingPosition.setEnabled(True)
            self.btn_goToLoadingPosition.setText(BTN_LOADING_POSITION_IDLE_UNLOADED)        
        
    def move_x_forward(self):
        """ callback to move forward in x """
        self.core.navigation.move_x(self.entry_dX.value())
    def move_x_backward(self):
        """ callback to move backward in x """
        self.core.navigation.move_x(-self.entry_dX.value())
    def move_y_forward(self):
        """ callback to move forward in y """
        self.core.navigation.move_y(self.entry_dY.value())
    def move_y_backward(self):
        """ callback to move backward in y """
        self.core.navigation.move_y(-self.entry_dY.value())
    def move_z_forward(self):
        """ callback to move forward in z """
        self.core.navigation.move_z(self.entry_dZ.value()/1000)
    def move_z_backward(self):
        """ callback to move backward in z """
        self.core.navigation.move_z(-self.entry_dZ.value()/1000)

    def set_pos_x(self,new_x:float):
        self.real_pos_x=new_x
        self.label_Xpos.setText(f"{new_x:.2f}".replace(".",","))
    def set_pos_y(self,new_y:float):
        self.real_pos_y=new_y
        self.label_Ypos.setText(f"{new_y:.2f}".replace(".",","))
    def set_pos_z(self,new_z:float):
        self.real_pos_z=new_z
        self.label_Zpos.setText(f"{(new_z-self.zero_z_offset):.2f}".replace(".",","))

    def zero_z(self,btn_state):
        if btn_state:
            self.zero_z_offset=self.real_pos_z
        else:
            self.zero_z_offset=0.0

        self.set_pos_z(self.real_pos_z)

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.btn_moveX_forward,
            self.btn_moveX_backward,
            self.btn_moveY_forward,
            self.btn_moveY_backward,
            self.btn_moveZ_forward,
            self.btn_moveZ_backward,
            self.btn_goToLoadingPosition,
        ]
