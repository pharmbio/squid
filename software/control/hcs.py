from multiprocessing.sharedctypes import Value
from qtpy.QtCore import Qt, QThread, QObject
from qtpy.QtWidgets import QApplication

# app specific libraries
from control._def import *
import control.camera as camera
import control.core as core
import control.microcontroller as microcontroller
import control.core_displacement_measurement as core_displacement_measurement

from control.typechecker import TypecheckFunction

from typing import List, Tuple, Callable

import numpy

class HCSController(QObject):
    def __init__(self,home:bool=True):
        super().__init__()

        if not home:
            print("warning: disabled homing on startup can lead to misalignment of the stage. proceed at your own risk. (may damage objective, and/or run into software stage position limits, which can lead to unexpected behaviour)")

        # load objects
        try:
            sn_camera_main = camera.get_sn_by_model(MACHINE_CONFIG.MAIN_CAMERA_MODEL)
            self.camera = camera.Camera(sn=sn_camera_main,rotate_image_angle=MACHINE_CONFIG.ROTATE_IMAGE_ANGLE,flip_image=MACHINE_CONFIG.FLIP_IMAGE)
            self.camera.open()
        except Exception as e:
            print('! imaging camera not detected !')
            raise e

        try:
            sn_camera_focus = camera.get_sn_by_model(MACHINE_CONFIG.FOCUS_CAMERA_MODEL)
            self.focus_camera = camera.Camera(sn=sn_camera_focus,used_for_laser_autofocus=True)
            self.focus_camera.open()
        except Exception as e:
            print('! laser AF camera not detected !')
            raise e

        try:
            self.microcontroller:microcontroller.Microcontroller = microcontroller.Microcontroller(version=MACHINE_CONFIG.CONTROLLER_VERSION)
        except Exception as e:
            print("! microcontroller not detected !")
            raise e

        # reset the MCU
        self.microcontroller.reset()
        # reinitialize motor drivers and DAC (in particular for V2.1 driver board where PG is not functional)
        self.microcontroller.initialize_drivers()
        # configure the actuators
        self.microcontroller.configure_actuators()

        self.configurationManager:    core.ConfigurationManager    = core.ConfigurationManager(filename='./channel_config_main_camera.json')
        self.streamHandler:           core.StreamHandler           = core.StreamHandler()
        self.liveController:          core.LiveController          = core.LiveController(self.camera,self.microcontroller,self.configurationManager,stream_handler=self.streamHandler)

        self.navigationController:    core.NavigationController    = core.NavigationController(self.microcontroller)
        self.autofocusController:     core.AutoFocusController     = core.AutoFocusController(self.camera,self.navigationController,self.liveController)

        LASER_AF_ENABLED=True
        if LASER_AF_ENABLED:
            # controllers
            self.configurationManager_focus_camera = core.ConfigurationManager(filename='./channel_config_focus_camera.json')
            self.streamHandler_focus_camera = core.StreamHandler()
            self.liveController_focus_camera = core.LiveController(self.focus_camera,self.microcontroller,self.configurationManager_focus_camera,stream_handler=self.streamHandler_focus_camera,control_illumination=False,for_displacement_measurement=True)

            self.displacementMeasurementController = core_displacement_measurement.DisplacementMeasurementController()
            self.laserAutofocusController = core.LaserAutofocusController(self.microcontroller,self.focus_camera,self.liveController_focus_camera,self.navigationController,has_two_interfaces=MACHINE_CONFIG.HAS_TWO_INTERFACES,use_glass_top=MACHINE_CONFIG.USE_GLASS_TOP)

            # camera
            self.focus_camera.set_software_triggered_acquisition() #self.camera.set_continuous_acquisition()
            self.focus_camera.set_callback(self.streamHandler_focus_camera.on_new_frame)
            self.focus_camera.enable_callback()

        self.multipointController:    core.MultiPointController    = core.MultiPointController(self.camera,self.navigationController,self.liveController,self.autofocusController,self.laserAutofocusController, self.configurationManager)
        self.imageSaver:              core.ImageSaver              = core.ImageSaver()

        # open the camera
        self.camera.set_software_triggered_acquisition()
        self.camera.set_callback(self.streamHandler.on_new_frame)
        self.camera.enable_callback()

        self.home_on_startup=home
        if home:
            self.home(home_x=MACHINE_CONFIG.HOMING_ENABLED_X,home_y=MACHINE_CONFIG.HOMING_ENABLED_Y,home_z=MACHINE_CONFIG.HOMING_ENABLED_Z)

        self.num_running_experiments=0

    # borrowed multipointController functions
    @property
    def set_NX(self):
        return self.multipointController.set_NX
    @property
    def set_NY(self):
        return self.multipointController.set_NY
    @property
    def set_NZ(self):
        return self.multipointController.set_NZ
    @property
    def set_Nt(self):
        return self.multipointController.set_Nt
    @property
    def set_deltaX(self):
        return self.multipointController.set_deltaX
    @property
    def set_deltaY(self):
        return self.multipointController.set_deltaY
    @property
    def set_deltaZ(self):
        return self.multipointController.set_deltaZ
    @property
    def set_deltat(self):
        return self.multipointController.set_deltat
    @property
    def set_selected_configurations(self):
        return self.multipointController.set_selected_configurations
    @property
    def set_software_af_flag(self):
        return self.multipointController.set_software_af_flag
    @property
    def set_laser_af_flag(self):
        return self.multipointController.set_laser_af_flag

    #borrowed navigationController functions
    @property
    def move_x(self):
        return self.navigationController.move_x
    @property
    def move_y(self):
        return self.navigationController.move_y
    @property
    def move_z(self):
        return self.navigationController.move_z
    @property
    def move_x_to(self):
        return self.navigationController.move_x_to
    @property
    def move_y_to(self):
        return self.navigationController.move_y_to
    @property
    def move_z_to(self):
        return self.navigationController.move_z_to
    @property
    def move_x_usteps(self):
        return self.navigationController.move_x_usteps
    @property
    def move_y_usteps(self):
        return self.navigationController.move_y_usteps
    @property
    def move_z_usteps(self):
        return self.navigationController.move_z_usteps
    @property
    def update_pos(self):
        return self.navigationController.update_pos
    @property
    def home_x(self):
        return self.navigationController.home_x
    @property
    def home_y(self):
        return self.navigationController.home_y
    @property
    def home_z(self):
        return self.navigationController.home_z
    @property
    def home_theta(self):
        return self.navigationController.home_theta
    @property
    def home_xy(self):
        return self.navigationController.home_xy
    @property
    def zero_x(self):
        return self.navigationController.zero_x
    @property
    def zero_y(self):
        return self.navigationController.zero_y
    @property
    def zero_z(self):
        return self.navigationController.zero_z
    @property
    def zero_theta(self):
        return self.navigationController.zero_theta
    @property
    def loading_position_enter(self):
        return self.navigationController.loading_position_enter
    @property
    def loading_position_leave(self):
        return self.navigationController.loading_position_leave
    @property
    def home(self):
        return self.navigationController.home
    @property
    def move_to(self):
        return self.navigationController.move_to

    #borrowed microcontroller functions
    @property
    def turn_on_illumination(self):
        return self.microcontroller.turn_on_illumination
    @property
    def turn_off_illumination(self):
        return self.microcontroller.turn_off_illumination
    @property
    def send_hardware_trigger(self):
        return self.microcontroller.send_hardware_trigger
    @property
    def wait_till_operation_is_completed(self):
        return self.microcontroller.wait_till_operation_is_completed
    @property
    def turn_on_AF_laser(self):
        return self.microcontroller.turn_on_AF_laser
    @property
    def turn_off_AF_laser(self):
        return self.microcontroller.turn_off_AF_laser
        
    #borrowed imageSaver functions
    #borrowed autofocusController functions
    #borrowed laserAutofocusController functions

    #@TypecheckFunction
    def acquire(self,
        well_list:List[Tuple[int,int]],
        channels:List[str],
        experiment_id:str,
        grid_data:Dict[str,dict]={
            'x':{'d':0.9,'N':1},
            'y':{'d':0.9,'N':1},
            'z':{'d':0.9,'N':1},
            't':{'d':0.9,'N':1},
        }, # todo add mask
        af_channel:Optional[str]=None, # software AF
        plate_type:ClosedSet[Optional[int]](None,6,12,24,96,384)=None,

        set_num_acquisitions_callback:Optional[Callable[[int],None]]=None,
        on_new_acquisition:Optional[Callable[[str],None]]=None,

        laser_af_on:bool=False,
        laser_af_initial_override=None,# override settings after initialization (i think thats sensor crop region + um/px estimated value)

        camera_pixel_format_override=None,
        trigger_override=None,

        grid_mask:Optional[Any]=None,

        headless:bool=True,
    )->Optional[QThread]:
        # set objective and well plate type from machine config (or.. should be part of imaging configuration..?)
        # set wells to be imaged <- acquire.well_list argument
        # set grid per well to be imaged
        # set lighting settings per channel
        # set selection and order of channels to be imaged <- acquire.channels argument

        # calculate physical imaging positions on wellplate given plate type and well selection
        wellplate_format=WELLPLATE_FORMATS[plate_type if not plate_type is None else MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT]

        # validate well positions (should be on the plate, given selected wellplate type)
        if wellplate_format.number_of_skip>0:
            for well_row,well_column in well_list:
                if well_row<0 or well_column<0:
                    raise ValueError(f"are you mad?! {well_row=} {well_column=}")

                if well_row>=wellplate_format.rows:
                    raise ValueError(f"{well_row=} is out of bounds {wellplate_format}")
                if well_column>=wellplate_format.columns:
                    raise ValueError(f"{well_column=} is out of bounds {wellplate_format}")

                if well_row<wellplate_format.number_of_skip:
                    raise ValueError(f"well {well_row=} out of bounds {wellplate_format}")
                if well_row>=(wellplate_format.rows-wellplate_format.number_of_skip):
                    raise ValueError(f"well {well_row=} out of bounds {wellplate_format}")

                if well_column<wellplate_format.number_of_skip:
                    raise ValueError(f"well {well_column=} out of bounds {wellplate_format}")
                if well_column>=(wellplate_format.columns-wellplate_format.number_of_skip):
                    raise ValueError(f"well {well_column=} out of bounds {wellplate_format}")

        well_list_names:List[str]=[wellplate_format.well_name(*c) for c in well_list]
        well_list_physical_pos:List[Tuple[float,float]]=[wellplate_format.convert_well_index(*c) for c in well_list]

        # print well names as debug info
        #print("imaging wells: ",", ".join(well_list_names))

        # set autofocus parameters
        if af_channel is None:
            self.multipointController.set_software_af_flag(False)
        else:
            assert af_channel in [c.name for c in self.configurationManager.configurations], f"{af_channel} is not a valid (AF) channel"
            if af_channel!=MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL:
                MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL=af_channel
            self.multipointController.set_software_af_flag(True)

        # set grid data per well
        self.set_NX(grid_data['x']['N'])
        self.set_NY(grid_data['y']['N'])
        self.set_NZ(grid_data['z']['N'])
        self.set_Nt(grid_data['t']['N'])
        self.set_deltaX(grid_data['x']['d'])
        self.set_deltaY(grid_data['y']['d'])
        self.set_deltaZ(grid_data['z']['d'])
        self.set_deltat(grid_data['t']['d'])

        for i,(well_row,well_column) in enumerate(well_list):
            well_x_mm,well_y_mm=well_list_physical_pos[i]
            for x_grid_item,y_grid_item in self.multipointController.grid_positions_for_well(well_x_mm,well_y_mm):
                if self.fov_exceeds_well_boundary(well_row,well_column,x_grid_item,y_grid_item):
                    raise ValueError(f"at least one grid item is outside the bounds of the well! well size is {wellplate_format.well_size_mm}mm")

        # set list of imaging channels
        self.set_selected_configurations(channels)

        # set image saving location
        self.multipointController.set_base_path(path=MACHINE_CONFIG.DISPLAY.DEFAULT_SAVING_PATH)
        self.multipointController.prepare_folder_for_new_experiment(experiment_ID=experiment_id) # todo change this to a callback (so that each image can be handled in a callback, not as batch or whatever)

        # start experiment, and return thread that actually does the imaging (thread.finished can be connected to some callback)
        return self.multipointController.run_experiment(
            well_selection=(well_list_names,well_list_physical_pos),
            set_num_acquisitions_callback=set_num_acquisitions_callback,
            on_new_acquisition=on_new_acquisition,
            grid_mask=grid_mask,
            headless=headless,
        )

    @TypecheckFunction
    def fov_exceeds_well_boundary(self,well_row:int,well_column:int,x_mm:float,y_mm:float)->bool:
        """
        check if a position on the plate exceeds the boundaries of a well
        (plate position in mm relative to plate origin. well position as row and column index, where row A and column 1 have index 0)
        """
        wellplate_format=WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT]

        well_center_x_mm,well_center_y_mm=wellplate_format.convert_well_index(well_row,well_column)

        # assuming wells are square (even though they are round-ish)
        well_left_boundary=well_center_x_mm-wellplate_format.well_size_mm/2
        well_right_boundary=well_center_x_mm+wellplate_format.well_size_mm/2
        assert well_left_boundary<well_right_boundary
        well_upper_boundary=well_center_y_mm+wellplate_format.well_size_mm/2
        well_lower_boundary=well_center_y_mm-wellplate_format.well_size_mm/2
        assert well_lower_boundary<well_upper_boundary

        is_in_bounds=x_mm>=well_left_boundary and x_mm<=well_right_boundary and y_mm<=well_upper_boundary and y_mm>=well_lower_boundary

        return not is_in_bounds

    @TypecheckFunction
    def close(self):
        # make sure the lasers are turned off!
        self.turn_off_illumination()

        if self.home_on_startup:
            # move the objective to a defined position upon exit
            self.move_x(0.1,{'timeout_limit_s':5, 'time_step':0.005}) # temporary bug fix - move_x needs to be called before move_x_to if the stage has been moved by the joystick
            self.move_x_to(30.0,{'timeout_limit_s':5, 'time_step':0.005})

            self.move_y(0.1,{'timeout_limit_s':5, 'time_step':0.005}) # temporary bug fix - move_y needs to be called before move_y_to if the stage has been moved by the joystick
            self.move_y_to(30.0,{'timeout_limit_s':5, 'time_step':0.005})

        self.liveController.stop_live()
        self.camera.close()
        self.focus_camera.close()
        self.imageSaver.close()
        self.microcontroller.close()

        QApplication.quit()

    
