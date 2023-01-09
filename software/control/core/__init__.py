# set QT_API environment variable
import os 
os.environ["QT_API"] = "pyqt5"

class StreamingCamera:
    def __init__(self,camera):
        self.camera=camera

    def __enter__(self):
        if not self.camera.in_a_state_to_be_used_directly:
            self.was_streaming=self.camera.is_streaming
            self.was_live=self.camera.is_live
            self.callback_was_enabled=self.camera.callback_is_enabled

            if self.callback_was_enabled:
                self.camera.disable_callback()
            if not self.was_live:
                self.camera.is_live=True
            if not self.was_streaming:
                self.camera.start_streaming()

            self.this_put_camera_into_a_state_to_be_used_directly=True
            self.camera.in_a_state_to_be_used_directly=True
        else:
            self.this_put_camera_into_a_state_to_be_used_directly=False

    def __exit__(self,_exception_type,_exception_value,_exception_traceback):
        if self.this_put_camera_into_a_state_to_be_used_directly:
            if self.was_streaming:
                self.camera.enable_callback()
            if not self.was_live:
                self.camera.is_live=False
            if not self.callback_was_enabled:
                self.camera.stop_streaming()

            self.camera.in_a_state_to_be_used_directly=False

            

from .stream_handler import StreamHandler
from .image_saver import ImageSaver
from .configuration import Configuration, ConfigurationManager
from .live import LiveController
from .navigation import NavigationController
from .autofocus import AutoFocusController
from .multi_point import MultiPointController
from .laser_autofocus import LaserAutofocusController

from multiprocessing.sharedctypes import Value
from qtpy.QtCore import Qt, QThread, QObject
from qtpy.QtWidgets import QApplication

# app specific libraries
from control._def import *
import control.camera as camera
import control.core as core
import control.microcontroller as microcontroller
from control.core.displacement_measurement import DisplacementMeasurementController

from control.typechecker import TypecheckFunction

from typing import List, Tuple, Callable

import numpy

class CameraWrapper:
    def __init__(self,
        camera,
        filename:str, # file backing up the configurations on disk
        microcontroller,
        use_streamhandler:bool=True, # use streamhandler by default to handle images

        **kwargs
    ):
        self.camera=camera
        self.microcontroller=microcontroller

        self.configuration_manager=core.ConfigurationManager(filename=filename)
        if use_streamhandler:
            self.stream_handler=core.StreamHandler()
        else:
            self.stream_handler=None

        self.live_controller=core.LiveController(
            self.camera,self.microcontroller,self.configuration_manager,
            stream_handler=self.stream_handler,
            **kwargs
        )

        self.camera.set_software_triggered_acquisition() # default trigger type
        if not self.stream_handler is None:
            self.camera.set_callback(self.stream_handler.on_new_frame)

        try:
            _=self.camera.wrapper
            camera_had_wrapper_before=True
        except:
            camera_had_wrapper_before=False

        if not camera_had_wrapper_before:
            self.camera.wrapper=self
        else:
            assert False, "a camera that already had a wrapper was attempted to be put inside a wrapper again"
        
    @property
    def pixel_formats(self)->List[str]:
        return list(self.camera.camera.PixelFormat.get_range().keys())

    def close(self):
        self.camera.close()
        self.live_controller.stop_live()

class Core(QObject):
    @property
    def camera(self):
        return self.main_camera.camera
    @property
    def configurationManager(self):
        return self.main_camera.configuration_manager
    @property
    def streamHandler(self):
        return self.main_camera.stream_handler
    @property
    def liveController(self):
        return self.main_camera.live_controller

    @property
    def configurationManager_focus_camera(self):
        return self.focus_camera.configuration_manager
    @property
    def streamHandler_focus_camera(self):
        return self.focus_camera.stream_handler
    @property
    def liveController_focus_camera(self):
        return self.focus_camera.live_controller

    def __init__(self,home:bool=True):
        super().__init__()

        if not home:
            print("warning: disabled homing on startup can lead to misalignment of the stage. proceed at your own risk. (may damage objective, and/or run into software stage position limits, which can lead to unexpected behaviour)")

        # load objects
        try:
            sn_camera_main = camera.get_sn_by_model(MACHINE_CONFIG.MAIN_CAMERA_MODEL)
            main_camera = camera.Camera(sn=sn_camera_main,rotate_image_angle=MACHINE_CONFIG.ROTATE_IMAGE_ANGLE,flip_image=MACHINE_CONFIG.FLIP_IMAGE)
            main_camera.open()
        except Exception as e:
            print('! imaging camera not detected !')
            raise e

        try:
            sn_camera_focus = camera.get_sn_by_model(MACHINE_CONFIG.FOCUS_CAMERA_MODEL)
            focus_camera = camera.Camera(sn=sn_camera_focus,used_for_laser_autofocus=True)
            focus_camera.open()
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
        self.microcontroller.configure_actuators()

        self.main_camera=CameraWrapper(
            camera=main_camera,
            filename='./channel_config_main_camera.json',
            microcontroller=self.microcontroller,
            use_streamhandler=True,
        )
        MACHINE_CONFIG.MUTABLE_STATE.trigger_mode_change.connect(lambda new_trigger_mode:self.main_camera.live_controller.set_trigger_mode(new_trigger_mode))

        self.focus_camera=CameraWrapper(
            camera=focus_camera,
            filename='./channel_config_focus_camera.json',
            microcontroller=self.microcontroller,
            use_streamhandler=True,

            control_illumination=False,
            for_displacement_measurement=True,
        )

        self.navigation:    core.NavigationController    = core.NavigationController(self.microcontroller)
        self.autofocusController:     core.AutoFocusController     = core.AutoFocusController(self.camera,self.navigation,self.liveController)

        LASER_AF_ENABLED=True
        if LASER_AF_ENABLED:
            self.displacementMeasurementController = DisplacementMeasurementController()
            self.laserAutofocusController = core.LaserAutofocusController(self.microcontroller,self.focus_camera.camera,self.liveController_focus_camera,self.navigation,has_two_interfaces=MACHINE_CONFIG.HAS_TWO_INTERFACES,use_glass_top=MACHINE_CONFIG.USE_GLASS_TOP)

        self.multipointController:    core.MultiPointController    = core.MultiPointController(self.camera,self.navigation,self.liveController,self.autofocusController,self.laserAutofocusController, self.configurationManager)
        self.imageSaver:              core.ImageSaver              = core.ImageSaver()

        self.home_on_startup=home
        if home:
            self.navigation.home(home_x=MACHINE_CONFIG.HOMING_ENABLED_X,home_y=MACHINE_CONFIG.HOMING_ENABLED_Y,home_z=MACHINE_CONFIG.HOMING_ENABLED_Z)

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
        },

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

        additional_data:Optional[dict]=None,
    )->Optional[QThread]:

        # set objective and well plate type from machine config (or.. should be part of imaging configuration..?)
        # set wells to be imaged <- acquire.well_list argument
        # set grid per well to be imaged
        # set lighting settings per channel
        # set selection and order of channels to be imaged <- acquire.channels argument

        # calculate physical imaging positions on wellplate given plate type and well selection
        plate_type=plate_type if not plate_type is None else MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT
        wellplate_format=WELLPLATE_FORMATS[plate_type]

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


        acquisition_data={
            "well_list":well_list_names,
            "experiment_id":experiment_id,
            "grid":{
                'x':{'d(mm)':grid_data['x']['d'],'N':grid_data['x']['N']},
                'y':{'d(mm)':grid_data['y']['d'],'N':grid_data['y']['N']},
                'z':{'d(um)':grid_data['z']['d']*1000,'N':grid_data['z']['N']},
                't':{'d(s)':grid_data['t']['d'],'N':grid_data['t']['N']},
            },
            "plate_type":str(plate_type),

            "channels_order":channels,
            "channel_config":self.configurationManager.configurations_list,

            "software_af_on":not af_channel is None,
            "software_af_channel":af_channel or "",

            "laser_af_on":laser_af_on,
        }
        
        if not additional_data is None:
            assert set(acquisition_data.keys()).isdisjoint(set(additional_data.keys())), "additional data provided to save as metadata overlaps primary data! (this is a bug)"
            acquisition_data.update(additional_data)

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
        self.multipointController.prepare_folder_for_new_experiment(experiment_ID=experiment_id,complete_experiment_data=acquisition_data) # todo change this to a callback (so that each image can be handled in a callback, not as batch or whatever)

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
            self.navigation.move_x(0.1,{'timeout_limit_s':5, 'time_step':0.005}) # temporary bug fix - move_x needs to be called before move_x_to if the stage has been moved by the joystick
            self.navigation.move_x_to(30.0,{'timeout_limit_s':5, 'time_step':0.005})

            self.navigation.move_y(0.1,{'timeout_limit_s':5, 'time_step':0.005}) # temporary bug fix - move_y needs to be called before move_y_to if the stage has been moved by the joystick
            self.navigation.move_y_to(30.0,{'timeout_limit_s':5, 'time_step':0.005})

        self.main_camera.close()
        self.focus_camera.close()

        self.imageSaver.close()
        self.microcontroller.close()

        QApplication.quit()

    
