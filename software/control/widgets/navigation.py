# qt libraries
from qtpy.QtWidgets import QFrame, QLabel, QDoubleSpinBox, QGridLayout, QMessageBox, QVBoxLayout, QApplication

from control._def import *
from control.gui import *
from control.core import Core

from typing import Optional, Union, List, Tuple

BTN_LOADING_POSITION_IDLE_UNLOADED="go to loading position"
BTN_LOADING_POSITION_IDLE_LOADED="leave loading position"
BTN_LOADING_POSITION_RUNNING="moving..."

class NavigationWidget(QFrame):
    @property
    def navigationController(self):
        return self.core.navigation

    def __init__(self, 
        core:Core,
    ):
        super().__init__()

        self.core=core

        self.label_Xpos = Label("0,0",text_selectable=True).widget
        self.label_Xpos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dX = SpinBoxDouble(minimum=0.0,maximum=25.0,step=0.2,default=1.0,num_decimals=3,keyboard_tracking=False).widget
        self.btn_moveX_forward = Button('Forward',on_clicked=self.move_x_forward).widget
        self.btn_moveX_backward = Button('Backward',on_clicked=self.move_x_backward).widget
        self.real_pos_x:float=0.0 # real x position of objective/slide in mm
        
        self.label_Ypos = Label("0,0",text_selectable=True).widget
        self.label_Ypos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dY = SpinBoxDouble(minimum=0.0,maximum=25.0,step=0.2,default=1.0,num_decimals=3,keyboard_tracking=False).widget
        self.btn_moveY_forward = Button('Forward',on_clicked=self.move_y_forward).widget
        self.btn_moveY_backward = Button('Backward',on_clicked=self.move_y_backward).widget
        self.real_pos_y:float=0.0 # real y position of objective/slide in mm

        self.label_Zpos = Label("0,0",text_selectable=True).widget
        self.label_Zpos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dZ = SpinBoxDouble(minimum=0.0,maximum=1000.0,step=0.2,default=10.0,num_decimals=3,keyboard_tracking=False).widget
        self.btn_moveZ_forward = Button('Forward',on_clicked=self.move_z_forward).widget
        self.btn_moveZ_backward = Button('Backward',on_clicked=self.move_z_backward).widget
        self.real_pos_z:float=0.0 # real z position of objective/slide in mm

        self.btn_zero_Z = Button('Zero Z',checkable=True,on_clicked=self.zero_z).widget
        self.zero_z_offset=0.0

        self.btn_goToLoadingPosition=Button(BTN_LOADING_POSITION_IDLE_UNLOADED).widget
        self.btn_goToLoadingPosition.clicked.connect(self.loading_position_toggle)
        
        if MACHINE_CONFIG.DISPLAY.SHOW_XY_MOVEMENT:
            grid_line0 = Grid([ QLabel('X (mm)'), self.label_Xpos, self.entry_dX, self.btn_moveX_forward, self.btn_moveX_backward, ]).layout
            grid_line1 = Grid([ QLabel('Y (mm)'), self.label_Ypos, self.entry_dY, self.btn_moveY_forward, self.btn_moveY_backward, ]).layout

        grid_line2 = Grid([ QLabel('Z (um)'), self.label_Zpos, self.entry_dZ, self.btn_moveZ_forward, self.btn_moveZ_backward, ]).layout
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

    def set_movement_ability(self,movement_allowed:bool,apply_to_loading_position_button:bool=False):
        for item in [
            self.btn_moveX_forward,
            self.btn_moveX_backward,
            self.btn_moveY_forward,
            self.btn_moveY_backward,
                    self.btn_moveZ_forward,
            self.btn_moveZ_backward,
            self.btn_zero_Z,
        ]:
            item.setDisabled(not movement_allowed)

        if apply_to_loading_position_button:
            self.btn_goToLoadingPosition.setDisabled(not movement_allowed)

    def loading_position_toggle(self,button_state:bool):
        self.btn_goToLoadingPosition.setDisabled(True)
        self.btn_goToLoadingPosition.setText(BTN_LOADING_POSITION_RUNNING)
        self.set_movement_ability(movement_allowed=False)

        if self.core.navigation.is_in_loading_position:
            self.core.navigation.loading_position_leave()
            self.btn_goToLoadingPosition.setText(BTN_LOADING_POSITION_IDLE_UNLOADED)
            self.set_movement_ability(movement_allowed=True)
        else:
            self.core.navigation.loading_position_enter()
            self.btn_goToLoadingPosition.setText(BTN_LOADING_POSITION_IDLE_LOADED)

        self.btn_goToLoadingPosition.setDisabled(False)
        
    def move_x_forward(self):
        self.core.navigation.move_x(self.entry_dX.value())
    def move_x_backward(self):
        self.core.navigation.move_x(-self.entry_dX.value())
    def move_y_forward(self):
        self.core.navigation.move_y(self.entry_dY.value())
    def move_y_backward(self):
        self.core.navigation.move_y(-self.entry_dY.value())
    def move_z_forward(self):
        self.core.navigation.move_z(self.entry_dZ.value()/1000)
    def move_z_backward(self):
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
