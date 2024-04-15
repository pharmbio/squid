# qt libraries
from qtpy.QtCore import QObject, Signal # type: ignore
from qtpy.QtWidgets import QApplication

from control._def import *

import time
import math

import typing as tp

import control.microcontroller as microcontroller
from control.typechecker import TypecheckFunction

class NavigationController(QObject):

    xPos = Signal(float)
    yPos = Signal(float)
    zPos = Signal(float)
    
    thetaPos = Signal(float)
    xyPos = Signal(float,float)
    signal_joystick_button_pressed = Signal()

    @TypecheckFunction
    def __init__(self,
        microcontroller:microcontroller.Microcontroller,
    ):
        QObject.__init__(self)
        self.microcontroller = microcontroller

        self.x_pos_mm = 0
        self.y_pos_mm = 0
        self.z_pos_mm = 0

        self.well_pos_is_stale:bool=True
        self.well_pos_row:int=0
        self.well_pos_column:int=0

        self.z_pos_usteps = 0
        self.theta_pos_rad = 0

        self.enable_joystick_button_action:bool = True

        # to be moved to gui for transparency
        self.microcontroller.set_callback(self.update_pos)

        self.is_in_loading_position:bool=False

    @property
    def plate_type(self)->WellplateFormatPhysical:
        return WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT]

    @TypecheckFunction
    def move_x(self,x_mm:float,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        self.move_x_usteps(self.microcontroller.mm_to_ustep_x(x_mm),wait_for_completion=wait_for_completion,wait_for_stabilization=wait_for_stabilization)

    @TypecheckFunction
    def move_y(self,y_mm:float,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        self.move_y_usteps(self.microcontroller.mm_to_ustep_y(y_mm),wait_for_completion=wait_for_completion,wait_for_stabilization=wait_for_stabilization)

    @TypecheckFunction
    def move_z(self,z_mm:float,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        """ this takes 210 ms ?! """
        self.move_z_usteps(self.microcontroller.mm_to_ustep_z(z_mm),wait_for_completion=wait_for_completion,wait_for_stabilization=wait_for_stabilization)

    @TypecheckFunction
    def move_x_usteps(self,usteps:int,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        self.microcontroller.move_x_usteps(usteps)
        if not wait_for_completion is None:
            self.microcontroller.wait_till_operation_is_completed(**wait_for_completion)
        if wait_for_stabilization:
            time.sleep(MACHINE_CONFIG.SCAN_STABILIZATION_TIME_MS_X/1000)

    @TypecheckFunction
    def move_y_usteps(self,usteps:int,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        self.microcontroller.move_y_usteps(usteps)
        if not wait_for_completion is None:
            self.microcontroller.wait_till_operation_is_completed(**wait_for_completion)
        if wait_for_stabilization:
            time.sleep(MACHINE_CONFIG.SCAN_STABILIZATION_TIME_MS_Y/1000)

    @TypecheckFunction
    def move_z_usteps(self,usteps:int,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        """ this takes 210 ms ?! """

        self.microcontroller.move_z_usteps(usteps)
        if not wait_for_completion is None:
            self.microcontroller.wait_till_operation_is_completed(**wait_for_completion)
        if wait_for_stabilization:
            time.sleep(MACHINE_CONFIG.SCAN_STABILIZATION_TIME_MS_Z/1000)

    @TypecheckFunction
    def move_x_to(self,x_mm:float,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        self.microcontroller.move_x_to_usteps(self.microcontroller.mm_to_ustep_x(x_mm))
        if not wait_for_completion is None:
            self.microcontroller.wait_till_operation_is_completed(**wait_for_completion)
        if wait_for_stabilization:
            time.sleep(MACHINE_CONFIG.SCAN_STABILIZATION_TIME_MS_X/1000)

    @TypecheckFunction
    def move_y_to(self,y_mm:float,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        self.microcontroller.move_y_to_usteps(self.microcontroller.mm_to_ustep_y(y_mm))
        if not wait_for_completion is None:
            self.microcontroller.wait_till_operation_is_completed(**wait_for_completion)
        if wait_for_stabilization:
            time.sleep(MACHINE_CONFIG.SCAN_STABILIZATION_TIME_MS_Y/1000)

    @TypecheckFunction
    def move_z_to(self,z_mm:float,wait_for_completion:tp.Optional[dict]=None,wait_for_stabilization:bool=False):
        self.microcontroller.move_z_to_usteps(self.microcontroller.mm_to_ustep_z(z_mm))
        if not wait_for_completion is None:
            self.microcontroller.wait_till_operation_is_completed(**wait_for_completion)
        if wait_for_stabilization:
            time.sleep(MACHINE_CONFIG.SCAN_STABILIZATION_TIME_MS_Z/1000)

    def move_to_name(self,wellplate_format,well_name):
        row,column=wellplate_format.well_name_to_index(well_name)

        self.move_to_index(wellplate_format,row=row,column=column)

    @TypecheckFunction
    def move_to_index(self,wellplate_format:WellplateFormatPhysical,row:int,column:int,well_origin_x_offset:float=0.0,well_origin_y_offset:float=0.0):
        # based on target row and column index, calculate target location in mm
        target_row,target_column=row,column
        target_x_mm,target_y_mm=wellplate_format.well_index_to_mm(row=target_row,column=target_column)
        target_x_mm+=well_origin_x_offset
        target_y_mm+=well_origin_y_offset

        self.move_to_mm(x_mm=target_x_mm,y_mm=target_y_mm,wait_for_completion={})
    
    @TypecheckFunction
    def move_by_mm(self,x_mm:tp.Optional[float]=None,y_mm:tp.Optional[float]=None,z_mm:tp.Optional[float]=None,wait_for_completion:Optional[dict]=None):
        self.move_to_mm(
            x_mm=None if x_mm is None else x_mm+self.x_pos_mm,
            y_mm=None if y_mm is None else y_mm+self.y_pos_mm,
            z_mm=None if z_mm is None else z_mm+self.z_pos_mm,
            wait_for_completion=wait_for_completion
        )

    @TypecheckFunction
    def move_to_mm(self,x_mm:tp.Optional[float]=None,y_mm:tp.Optional[float]=None,z_mm:tp.Optional[float]=None,wait_for_completion:Optional[dict]=None):
        if not x_mm is None and not y_mm is None:
            def distance_to_wellplate_center(y_mm:float,x_mm:float)->float:
                """ calculate distance of any point on the plate to the center of the wellplate """

                # calculate center coordinates of the wellplate based on calibrated limits
                plate_limits=self.plate_type.limit_unsafe(calibrated=True)
                y_center=plate_limits.Y_NEGATIVE+(plate_limits.Y_POSITIVE-plate_limits.Y_NEGATIVE)/2
                x_center=plate_limits.X_NEGATIVE+(plate_limits.X_POSITIVE-plate_limits.X_NEGATIVE)/2

                return ((y_mm-y_center)**2+(x_mm-x_center)**2)**0.5
            
            # rename some things for better code readability
            target_x_mm=x_mm
            target_y_mm=y_mm
            current_x_mm=self.x_pos_mm
            current_y_mm=self.y_pos_mm

            # calculate distance of both possible edge points (well where movement in x/y is done and movement in y/x starts, respectively) to the center of the wellplate
            d1=distance_to_wellplate_center(current_y_mm,target_x_mm)
            d2=distance_to_wellplate_center(target_y_mm,current_x_mm)
            
            # move to the edge point that is closer to the center of the wellplate
            # because this point will always avoid moving the objective over/through the forbidden edge areas on the wellplate (since any point on the wellplate is closer to the center than the points on the edge..)
            if d1<d2:
                # move to target column while staying in current row first
                self.move_x_to(target_x_mm,wait_for_completion=wait_for_completion)
                # then move to target row
                self.move_y_to(target_y_mm,wait_for_completion=wait_for_completion,wait_for_stabilization=True)
            else:
                # move to target row while staying in current column first
                self.move_y_to(target_y_mm,wait_for_completion=wait_for_completion)
                # then move to target column
                self.move_x_to(target_x_mm,wait_for_completion=wait_for_completion,wait_for_stabilization=True)
        else:
            if not x_mm is None:
                self.move_x_to(x_mm,wait_for_completion=wait_for_completion,wait_for_stabilization=y_mm is None)
            if not y_mm is None:
                self.move_y_to(y_mm,wait_for_completion=wait_for_completion,wait_for_stabilization=True)

        if not z_mm is None:
            self.move_y_to(y_mm,wait_for_completion=wait_for_completion,wait_for_stabilization=True)

    @TypecheckFunction
    def update_pos(self,microcontroller:microcontroller.Microcontroller):
        """ this function will be called around every 10ms """

        # get position from the microcontroller
        x_pos, y_pos, z_pos, theta_pos = microcontroller.get_pos()
        self.z_pos_usteps = z_pos
        
        # calculate position in mm or rad
        self.x_pos_mm = self.microcontroller.ustep_to_mm_x(x_pos)
        self.y_pos_mm = self.microcontroller.ustep_to_mm_y(y_pos)
        self.z_pos_mm = self.microcontroller.ustep_to_mm_z(z_pos)

        if MACHINE_CONFIG.USE_ENCODER_THETA:
            self.theta_pos_rad = theta_pos*MACHINE_CONFIG.ENCODER_POS_SIGN_THETA*MACHINE_CONFIG.ENCODER_STEP_SIZE_THETA
        else:
            self.theta_pos_rad = theta_pos*MACHINE_CONFIG.STAGE_POS_SIGN_THETA*(2*math.pi/(MACHINE_CONFIG.MICROSTEPPING_DEFAULT_THETA*MACHINE_CONFIG.FULLSTEPS_PER_REV_THETA))

        wellplate_format=WELLPLATE_FORMATS["Generic 384"]
        wellplate_format.pos_mm_to_well_index(x_mm=self.x_pos_mm,y_mm=self.y_pos_mm)

        # emit the updated position
        self.xPos.emit(self.x_pos_mm)
        self.yPos.emit(self.y_pos_mm)
        self.zPos.emit(self.z_pos_mm*1000)
        self.thetaPos.emit(self.theta_pos_rad*360/(2*math.pi))
        self.xyPos.emit(self.x_pos_mm,self.y_pos_mm)

        if microcontroller.signal_joystick_button_pressed_event:
            if self.enable_joystick_button_action:
                self.signal_joystick_button_pressed.emit()
            print('joystick button pressed')
            microcontroller.signal_joystick_button_pressed_event = False

        QApplication.processEvents()
        

    #def home_theta(self):
    #    self.microcontroller.home_theta()

    def loading_position_enter(self,home_x:bool=True,home_y:bool=True,home_z:bool=True):
        # if used through GUI, this should never be the case
        # but the API must account for this function being called twice
        if self.is_in_loading_position:
            MAIN_LOG.log("tried to enter loading position when already in loading position")
            return

        if home_z:
			# retract the objective
            self.microcontroller.home_z()
			# wait for the operation to finish
            self.microcontroller.wait_till_operation_is_completed(10, time_step=0.005, timeout_msg='z homing timeout, the program will exit')

            self.is_in_loading_position=True

            MAIN_LOG.log('homing - objective retracted')

            if home_z and home_y and home_x:
                # for the new design, need to home y before home x; x also needs to be at > + 10 mm when homing y
                self.move_x(12.0)
                self.microcontroller.wait_till_operation_is_completed(10, time_step=0.005, timeout_msg='x moving timeout, the program will exit')
                
                self.microcontroller.home_y()
                self.microcontroller.wait_till_operation_is_completed(10, time_step=0.005, timeout_msg='y homing timeout, the program will exit')
                
                self.microcontroller.home_x()
                self.microcontroller.wait_till_operation_is_completed(10, time_step=0.005, timeout_msg='x homing timeout, the program will exit')

                MAIN_LOG.log("homing - in loading position")

    def loading_position_leave(self,home_x:bool=True,home_y:bool=True,home_z:bool=True):
        if not self.is_in_loading_position:
            MAIN_LOG.log("tried to leave loading position while not actually in loading position")
            return

        if home_z:
            if home_z and home_y and home_x:
                # move by (from home to) (20 mm, 20 mm)
                self.move_x(x_mm=20.0,wait_for_completion={'timeout_limit_s':10, 'time_step':0.005})
                self.move_y(y_mm=20.0,wait_for_completion={'timeout_limit_s':10, 'time_step':0.005})
            
                self.set_x_limit_pos_mm(MACHINE_CONFIG.SOFTWARE_POS_LIMIT.X_POSITIVE)
                self.set_x_limit_neg_mm(MACHINE_CONFIG.SOFTWARE_POS_LIMIT.X_NEGATIVE)
                self.set_y_limit_pos_mm(MACHINE_CONFIG.SOFTWARE_POS_LIMIT.Y_POSITIVE)
                self.set_y_limit_neg_mm(MACHINE_CONFIG.SOFTWARE_POS_LIMIT.Y_NEGATIVE)
                self.set_z_limit_pos_mm(MACHINE_CONFIG.SOFTWARE_POS_LIMIT.Z_POSITIVE)

                MAIN_LOG.log("homing - left loading position")

			# move the objective back
            self.move_z(MACHINE_CONFIG.DEFAULT_Z_POS_MM)
			# wait for the operation to finish
            self.microcontroller.wait_till_operation_is_completed(10, time_step=0.005, timeout_msg='z return timeout, the program will exit')

            self.is_in_loading_position=False

            MAIN_LOG.log("homing - objective raised")


    def home(self,home_x:bool=True,home_y:bool=True,home_z:bool=True):
        self.loading_position_enter(home_x,home_y,home_z)
        self.loading_position_leave(home_x,home_y,home_z)

    def set_x_limit_pos_mm(self,value_mm):
        u_steps=int(value_mm/self.microcontroller.mm_per_ustep_x)
        limit_code=LIMIT_CODE.X_POSITIVE if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_X > 0 else LIMIT_CODE.X_NEGATIVE
        u_steps_factor=1 if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_X > 0 else MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_X

        self.microcontroller.set_lim(limit_code,u_steps_factor*u_steps)

    def set_x_limit_neg_mm(self,value_mm):
        u_steps=int(value_mm/self.microcontroller.mm_per_ustep_x)
        limit_code=LIMIT_CODE.X_NEGATIVE if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_X > 0 else LIMIT_CODE.X_POSITIVE
        u_steps_factor=1 if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_X > 0 else MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_X

        self.microcontroller.set_lim(limit_code,u_steps_factor*u_steps)

    def set_y_limit_pos_mm(self,value_mm):
        u_steps=int(value_mm/self.microcontroller.mm_per_ustep_y)
        limit_code=LIMIT_CODE.Y_POSITIVE if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Y > 0 else LIMIT_CODE.Y_NEGATIVE
        u_steps_factor=1 if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Y > 0 else MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Y

        self.microcontroller.set_lim(limit_code,u_steps_factor*u_steps)

    def set_y_limit_neg_mm(self,value_mm):
        u_steps=int(value_mm/self.microcontroller.mm_per_ustep_y)
        limit_code=LIMIT_CODE.Y_NEGATIVE if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Y > 0 else LIMIT_CODE.Y_POSITIVE
        u_steps_factor=1 if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Y > 0 else MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Y

        self.microcontroller.set_lim(limit_code,u_steps_factor*u_steps)

    def set_z_limit_pos_mm(self,value_mm):
        u_steps=int(value_mm/self.microcontroller.mm_per_ustep_z)
        limit_code=LIMIT_CODE.Z_POSITIVE if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Z > 0 else LIMIT_CODE.Z_NEGATIVE
        u_steps_factor=1 if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Z > 0 else MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Z

        self.microcontroller.set_lim(limit_code,u_steps_factor*u_steps)

    def set_z_limit_neg_mm(self,value_mm):
        u_steps=int(value_mm/self.microcontroller.mm_per_ustep_z)
        limit_code=LIMIT_CODE.Z_NEGATIVE if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Z > 0 else LIMIT_CODE.Z_POSITIVE
        u_steps_factor=1 if MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Z > 0 else MACHINE_CONFIG.STAGE_MOVEMENT_SIGN_Z

        self.microcontroller.set_lim(limit_code,u_steps_factor*u_steps)
