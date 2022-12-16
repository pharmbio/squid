# qt libraries
from qtpy.QtWidgets import QFrame, QLabel, QDoubleSpinBox, QGridLayout, QMessageBox, QVBoxLayout, QApplication

from control._def import *
from control.gui import *

from typing import Optional, Union, List, Tuple

BTN_LOADING_POSITION_IDLE_UNLOADED="go to loading position"
BTN_LOADING_POSITION_IDLE_LOADED="leave loading position"
BTN_LOADING_POSITION_RUNNING="moving..."

class NavigationWidget(QFrame):
    @property
    def navigationController(self):
        return self.core.navigation

    def __init__(self, 
        core, 
        gui,
        widget_configuration:str,
    ):
        super().__init__()

        self.core=core
        self.gui=gui

        self.widget_configuration = widget_configuration

        self.label_Xpos = Label("0,0",text_selectable=True).widget
        self.label_Xpos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dX = SpinBoxDouble(minimum=0.0,maximum=25.0,step=0.2,default=1.0,num_decimals=3,keyboard_tracking=False,on_valueChanged=self.set_deltaX).widget
        self.btn_moveX_forward = Button('Forward',on_clicked=self.move_x_forward).widget
        self.btn_moveX_backward = Button('Backward',on_clicked=self.move_x_backward).widget
        
        self.label_Ypos = Label("0,0",text_selectable=True).widget
        self.label_Ypos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dY = SpinBoxDouble(minimum=0.0,maximum=25.0,step=0.2,default=1.0,num_decimals=3,keyboard_tracking=False,on_valueChanged=self.set_deltaY).widget
        self.btn_moveY_forward = Button('Forward',on_clicked=self.move_y_forward).widget
        self.btn_moveY_backward = Button('Backward',on_clicked=self.move_y_backward).widget

        self.label_Zpos = Label("0,0",text_selectable=True).widget
        self.label_Zpos.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.entry_dZ = SpinBoxDouble(minimum=0.0,maximum=1000.0,step=0.2,default=10.0,num_decimals=3,keyboard_tracking=False,on_valueChanged=self.set_deltaZ).widget
        self.btn_moveZ_forward = Button('Forward',on_clicked=self.move_z_forward).widget
        self.btn_moveZ_backward = Button('Backward',on_clicked=self.move_z_backward).widget

        self.btn_zero_Z = Button('Zero Z',checkable=True,on_clicked=self.zero_z).widget
        self.zero_z_offset=0.0

        self.btn_goToLoadingPosition=Button(BTN_LOADING_POSITION_IDLE_UNLOADED).widget
        self.btn_goToLoadingPosition.clicked.connect(self.loading_position_toggle)
        
        if MACHINE_CONFIG.DISPLAY.SHOW_XY_MOVEMENT:
            grid_line0 = Grid([ QLabel('X (mm)'), self.label_Xpos, self.entry_dX, self.btn_moveX_forward, self.btn_moveX_backward, ]).layout
            grid_line1 = Grid([ QLabel('Y (mm)'), self.label_Ypos, self.entry_dY, self.btn_moveY_forward, self.btn_moveY_backward, ]).layout
        grid_line2 = Grid([ QLabel('Z (um)'), self.label_Zpos, self.entry_dZ, self.btn_moveZ_forward, self.btn_moveZ_backward, ]).layout
        
        if self.widget_configuration in (WELLPLATE_NAMES[384], WELLPLATE_NAMES[96]):
            grid_line3 = Grid([ self.btn_zero_Z, self.btn_goToLoadingPosition ]).layout
        else:
            err_msg=f"{self.widget_configuration} is not a supported NavigationViewer configuration"
            raise Exception(err_msg)

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
        self.grid = Grid(*grid_lines).layout
        self.setLayout(self.grid)

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

        QApplication.processEvents()

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

    def set_deltaX(self,value):
        mm_per_ustep = self.core.microcontroller.mm_per_ustep_x
        deltaX = round(value/mm_per_ustep)*mm_per_ustep
        self.entry_dX.setValue(deltaX)
    def set_deltaY(self,value):
        mm_per_ustep = self.core.microcontroller.mm_per_ustep_y
        deltaY = round(value/mm_per_ustep)*mm_per_ustep
        self.entry_dY.setValue(deltaY)
    def set_deltaZ(self,value):
        mm_per_ustep = self.core.microcontroller.mm_per_ustep_z
        deltaZ = round(value/1000/mm_per_ustep)*mm_per_ustep*1000
        self.entry_dZ.setValue(deltaZ)

    def set_pos_x(self,new_x):
        self.real_pos_x=new_x
        self.label_Xpos.setText(f"{new_x:.2f}".replace(".",","))
    def set_pos_y(self,new_y):
        self.real_pos_y=new_y
        self.label_Ypos.setText(f"{new_y:.2f}".replace(".",","))
    def set_pos_z(self,new_z):
        self.real_pos_z=new_z
        self.label_Zpos.setText(f"{(new_z-self.zero_z_offset):.2f}".replace(".",","))

    def zero_z(self,btn_state):
        if btn_state:
            self.zero_z_offset=self.real_pos_z
        else:
            self.zero_z_offset=0.0

        self.set_pos_z(self.real_pos_z)

import pyqtgraph as pg
import numpy as np
import cv2
from enum import Enum

class Color(tuple,Enum):
    LIGHT_BLUE=(0xAD,0xD8,0xE6)
    RED=(255,0,0)
    LIGHT_GREY=(160,)*3


class NavigationViewer(QFrame):

    def __init__(self, sample:str, invertX:bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFrameStyle(QFrame.Panel | QFrame.Raised)

        # interpret image data as row-major instead of col-major
        pg.setConfigOptions(imageAxisOrder='row-major')
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.graphics_widget.setBackground("w")
        ## lock the aspect ratio so pixels are always square
        self.graphics_widget.view = self.graphics_widget.addViewBox(invertX=invertX,invertY=True,lockAspect=True)
        ## Create image item
        self.graphics_widget.img = pg.ImageItem(border='w')
        self.graphics_widget.view.addItem(self.graphics_widget.img)
        # make sure plate view is always visible, from view.getState()['viewRange']:
        max_state=[[-70.74301114861895, 1579.743011148619], [-254.9490586181788, 1264.9490586181787]] # furthest zoomed out
        min_state=[[733.5075292478979, 886.8248563569729], [484.2505774030056, 639.926632621451]] # furthest zoomed in
        ((max_lowerx,max_upperx),(max_lowery,max_uppery))=max_state
        ((min_lowerx,min_upperx),(min_lowery,min_uppery))=min_state
        self.graphics_widget.view.setLimits(
            #xMin=max_lowerx,
            #xMax=max_upperx,
            yMin=max_lowery,
            yMax=max_uppery,

            minXRange=min_upperx-min_lowerx,
            #maxXRange=max_upperx-max_lowerx,
            minYRange=min_uppery-min_lowery,
            maxYRange=max_uppery-max_lowery,
        )

        self.grid = QVBoxLayout()
        self.grid.addWidget(self.graphics_widget)
        self.setLayout(self.grid)
 
        self.last_fov_drawn=None
        self.set_wellplate_type(sample)
 
        self.location_update_threshold_mm = 0.4    
 
        self.box_color = Color.RED
        self.box_line_thickness = 2
 
        self.x_mm = None
        self.y_mm = None
 
        self.update_display()

        self.preview_fovs=[]

        MACHINE_CONFIG.MUTABLE_STATE.wellplate_format_change.connect(self.set_wellplate_type)

    def set_wellplate_type(self,wellplate_type:Union[str,int]):
        if type(wellplate_type)==int:
            new_wellplate_type=WELLPLATE_NAMES[wellplate_type]
        else:
            new_wellplate_type=wellplate_type

        wellplate_type_image={
            WELLPLATE_NAMES[384] : 'images/384_well_plate_1509x1010.png',
            WELLPLATE_NAMES[96]  : 'images/96_well_plate_1509x1010.png',
            WELLPLATE_NAMES[24]  : 'images/24_well_plate_1509x1010.png',
            WELLPLATE_NAMES[12]  : 'images/12_well_plate_1509x1010.png',
            WELLPLATE_NAMES[6]   : 'images/6_well_plate_1509x1010.png'
        }
        assert new_wellplate_type in wellplate_type_image, f"{new_wellplate_type} is not a valid plate type"
 
        self.background_image=cv2.imread(wellplate_type_image[new_wellplate_type])
 
        # current image is..
        self.current_image = np.copy(self.background_image)
        # current image display is..
        self.current_image_display = np.copy(self.background_image)
        self.image_height = self.background_image.shape[0]
        self.image_width = self.background_image.shape[1]
 
        self.sample = new_wellplate_type
 
        camera_pixel_size_um=MachineConfiguration.CAMERA_PIXEL_SIZE_UM[MACHINE_CONFIG.CAMERA_SENSOR]
        
        self.location_update_threshold_mm = 0.05
        WELLPLATE_IMAGE_LENGTH_IN_PIXELS=1509 # images in path(software/images) are 1509x1010
        WELLPLATE_384_LENGTH_IN_MM=127.8 # from https://www.thermofisher.com/document-connect/document-connect.html?url=https://assets.thermofisher.com/TFS-Assets%2FLSG%2Fmanuals%2Fcms_042831.pdf
        self.mm_per_pixel = WELLPLATE_384_LENGTH_IN_MM/WELLPLATE_IMAGE_LENGTH_IN_PIXELS # 0.084665 was the hardcoded value, which is closer to this number as calculated from the width of the plate at 85.5mm/1010px=0.0846535
        self.fov_size_mm = 3000*camera_pixel_size_um/(50/10)/1000 # '50/10' = tube_lens_mm/objective_magnification ?
        self.origin_bottom_left_x = MACHINE_CONFIG.X_ORIGIN_384_WELLPLATE_PIXEL - (MACHINE_CONFIG.X_MM_384_WELLPLATE_UPPERLEFT)/self.mm_per_pixel
        self.origin_bottom_left_y = MACHINE_CONFIG.Y_ORIGIN_384_WELLPLATE_PIXEL - (MACHINE_CONFIG.Y_MM_384_WELLPLATE_UPPERLEFT)/self.mm_per_pixel
 
        self.clear_imaged_positions()
 
    @TypecheckFunction
    def update_current_location(self,x_mm:Optional[float],y_mm:Optional[float]):
        if self.x_mm != None and self.y_mm != None:
            # update only when the displacement has exceeded certain value
            if abs(x_mm - self.x_mm) > self.location_update_threshold_mm or abs(y_mm - self.y_mm) > self.location_update_threshold_mm:
                self.draw_current_fov(x_mm,y_mm)
                self.update_display()
                self.x_mm = x_mm
                self.y_mm = y_mm
        else:
            self.draw_current_fov(x_mm,y_mm)
            self.update_display()
            self.x_mm = x_mm
            self.y_mm = y_mm

    @TypecheckFunction
    def coord_to_bb(self,x_mm:float,y_mm:float)->Tuple[Tuple[int,int],Tuple[int,int]]:
        topleft_x:int=round(self.origin_bottom_left_x + x_mm/self.mm_per_pixel - self.fov_size_mm/2/self.mm_per_pixel)
        topleft_y:int=round((self.origin_bottom_left_y + y_mm/self.mm_per_pixel) - self.fov_size_mm/2/self.mm_per_pixel)

        top_left = (topleft_x,topleft_y)

        bottomright_x:int=round(self.origin_bottom_left_x + x_mm/self.mm_per_pixel + self.fov_size_mm/2/self.mm_per_pixel)
        bottomright_y:int=round((self.origin_bottom_left_y + y_mm/self.mm_per_pixel) + self.fov_size_mm/2/self.mm_per_pixel)

        bottom_right = (bottomright_x,bottomright_y)

        return top_left,bottom_right

    def clear_imaged_positions(self):
        self.current_image = np.copy(self.background_image)
        if not self.last_fov_drawn is None:
            self.draw_current_fov(*self.last_fov_drawn)
        self.update_display()

    def update_display(self):
        """
        needs to be called when self.current_image_display has been flushed
        e.g. after self.draw_current_fov() or self.clear_slide(), which is done currently
        """
        self.graphics_widget.img.setImage(self.current_image_display,autoLevels=False)

    def clear_slide(self):
        self.current_image = np.copy(self.background_image)
        self.current_image_display = np.copy(self.background_image)
        self.update_display()
    
    # this is used to draw an arbitrary fov onto the displayed image view
    @TypecheckFunction
    def draw_fov(self,x_mm:float,y_mm:float,color:Tuple[int,int,int],foreground:bool=True):
        current_FOV_top_left, current_FOV_bottom_right=self.coord_to_bb(x_mm,y_mm)
        if foreground:
            img_target=self.current_image_display
        else:
            img_target=self.current_image
        cv2.rectangle(img_target, current_FOV_top_left, current_FOV_bottom_right, color, self.box_line_thickness)

    # this is used to draw the fov when running acquisition
    # draw onto background buffer so that when live view is updated, the live view fov is drawn on top of the already imaged positions
    @TypecheckFunction
    def register_fov(self,x_mm:float,y_mm:float,color:Tuple[int,int,int] = Color.LIGHT_BLUE):
        current_FOV_top_left, current_FOV_bottom_right=self.coord_to_bb(x_mm,y_mm)
        cv2.rectangle(self.current_image, current_FOV_top_left, current_FOV_bottom_right, color, self.box_line_thickness)

    def register_preview_fovs(self):
        for x,y in self.preview_fovs:
            self.draw_fov(x,y,Color.LIGHT_GREY,foreground=False)

    # this is used to draw the fov when moving around live
    @TypecheckFunction
    def draw_current_fov(self,x_mm:float,y_mm:float):
        self.current_image_display = np.copy(self.current_image)
        self.draw_fov(x_mm,y_mm,self.box_color)
        self.update_display()

        self.last_fov_drawn=(x_mm,y_mm)
