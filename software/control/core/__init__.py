# set QT_API environment variable
import os 
os.environ["QT_API"] = "pyqt5"

from control._def import *
from control.typechecker import TypecheckFunction, TypecheckClass
from .configuration import Configuration, ConfigurationManager

from typing import List, Tuple, Callable, Optional

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

@TypecheckClass
class GridDimensionConfig:
    d:float
    N:int
    unit:str

    def as_json(self)->dict:
        return {
            "d":self.d,
            "N":self.N,
            "unit":self.unit
        }

    def from_json(s:dict)->"GridDimensionConfig":
        return GridDimensionConfig(
            d=s["d"],
            N=s["N"],
            unit=s["unit"],
        )

@TypecheckClass
class WellGridConfig:
    x:GridDimensionConfig
    y:GridDimensionConfig
    z:GridDimensionConfig
    t:GridDimensionConfig

    def as_json(self)->dict:
        return {
            "x":self.x.as_json(),
            "y":self.y.as_json(),
            "z":self.z.as_json(),
            "t":self.t.as_json(),
        }

    def from_json(s:dict)->"WellGridConfig":
        return WellGridConfig(
            x=GridDimensionConfig.from_json(s["x"]),
            y=GridDimensionConfig.from_json(s["y"]),
            z=GridDimensionConfig.from_json(s["z"]),
            t=GridDimensionConfig.from_json(s["t"])
        )

@TypecheckClass
class LaserAutofocusData:
    x_reference:float
    um_per_px:float

    x_offset:int
    y_offset:int
    x_width:int
    y_width:int

    has_two_interfaces:bool
    use_glass_top:bool

    def as_json(self)->dict:
        return {
            "x_reference":self.x_reference,
            "um_per_px":self.um_per_px,

            "x_offset":self.x_offset,
            "y_offset":self.y_offset,
            "x_width":self.x_width,
            "y_width":self.y_width,

            "has_two_interfaces":self.has_two_interfaces,
            "use_glass_top":self.use_glass_top,
        }

    def from_json(s:dict)->"LaserAutofocusData":
        return LaserAutofocusData(
            x_reference=s["x_reference"],
            um_per_px=s["um_per_px"],

            x_offset=s["x_offset"],
            y_offset=s["y_offset"],
            x_width=s["x_width"],
            y_width=s["y_width"],

            has_two_interfaces=s["has_two_interfaces"],
            use_glass_top=s["use_glass_top"],
        )

@TypecheckClass
class AcquisitionConfig:
    output_path:str
    project_name:str
    plate_name:str
    well_list:List[Tuple[int,int]]
    grid_mask:List[List[bool]]
    grid_config:WellGridConfig
    af_software_channel:Optional[str]=None
    af_laser_on:bool
    af_laser_reference:Optional[LaserAutofocusData]=None
    trigger_mode:TriggerMode
    pixel_format:str
    plate_type:int
    channels_ordered:List[str]
    channels_config:List[Configuration]
    image_file_format:ImageFormat

    def from_json(file_path:Union[str,Path])->"AcquisitionConfig":
        with open(str(file_path),mode="r",encoding="utf-8") as json_file:
            data=json.decoder.JSONDecoder().decode(json_file.read())

        well_list=data["well_list"]
        for i in range(len(well_list)):
            well=well_list[i]

            if isinstance(well,str):
                assert len(well)==3
                row=ord(well[0])-ord('A')
                assert row>=0
                column=int(well[1:])
                assert column>=0
            else:
                row,column=well

            well_list[i]=(row,column-1) # column-1 because on the wellplates the column indices start at 1 (while in code they start at 0)

        af_laser_reference=None
        if "af_laser_reference" in data and not data["af_laser_reference"] is None:
            af_laser_reference=LaserAutofocusData.from_json(data["af_laser_reference"])

        config=AcquisitionConfig(
            output_path=data["output_path"],
            project_name=data["project_name"],
            plate_name=data["plate_name"],
            well_list=well_list,
            grid_mask=data["grid_mask"],
            grid_config=WellGridConfig.from_json(data["grid_config"]),
            af_software_channel=data["af_software_channel"],
            af_laser_on=data["af_laser_on"],
            af_laser_reference=af_laser_reference,
            trigger_mode=TriggerMode(data["trigger_mode"]),
            pixel_format=data["pixel_format"],
            plate_type=data["plate_type"],
            channels_ordered=data["channels_ordered"],
            channels_config=[Configuration.from_json(config_dict) for config_dict in data["channels_config"]],
            image_file_format=[image_format for image_format in ImageFormat if image_format.name==data["image_file_format"]][0]
        )

        return config

    def as_json(self,well_index_to_name:bool=False)->dict:
        well_list=self.well_list
        if well_index_to_name:
            well_list=[f"{chr(w_row+ord('A'))}{w_column+1:02}" for w_row,w_column in well_list] # column+1 because on the wellplates the column indices start at 1 (while in code they start at 0)

        return {
            "output_path":self.output_path,
            "project_name":self.project_name,
            "plate_name":self.plate_name,

            "image_file_format":self.image_file_format.name,
            "trigger_mode":self.trigger_mode,
            "pixel_format":self.pixel_format,
            "plate_type":self.plate_type,

            "af_software_channel":self.af_software_channel,
            "af_laser_on":self.af_laser_on,
            "af_laser_reference":self.af_laser_reference.as_json() if not self.af_laser_reference is None else None,

            "grid_config":self.grid_config.as_json(),
            "grid_mask":self.grid_mask,
            "channels_ordered":self.channels_ordered,
            "channels_config":[config.as_dict() for config in self.channels_config],
            "well_list":well_list,
        }

    def save_json(self,file_path:Union[str,Path],well_index_to_name:bool=False):
        json_tree_string=json.encoder.JSONEncoder(indent=2).encode(self.as_json(well_index_to_name=well_index_to_name))

        with open(str(file_path), mode="w", encoding="utf-8") as json_file:
            json_file.write(json_tree_string)

@TypecheckClass
class ReferenceFile:
    path:Union[Path,str]

    plate_type:str
    cell_line:str

    def as_json(self)->dict:
        return {
            'path':str(self.path),
            'plate_type':self.plate_type,
            'cell_line':self.cell_line
        }
    def from_json(s:dict)->"ReferenceFile":
        return ReferenceFile(
            path=s["path"],
            plate_type=s["plate_type"],
            cell_line=s["cell_line"],
        )


from .stream_handler import StreamHandler
from .image_saver import ImageSaver
from .live import LiveController
from .navigation import NavigationController
from .autofocus import AutoFocusController
from .multi_point import MultiPointController
from .laser_autofocus import LaserAutofocusController

from qtpy.QtCore import Qt, QThread, QObject
from qtpy.QtWidgets import QApplication

# app specific libraries
import control.camera as camera
import control.core as core
import control.microcontroller as microcontroller
from control.core.displacement_measurement import DisplacementMeasurementController

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

    @property
    def plate_type(self)->int:
        return MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT

    #@TypecheckFunction
    def acquire(self,
        config:AcquisitionConfig,

        set_num_acquisitions_callback:Optional[Callable[[int],None]]=None,
        on_new_acquisition:Optional[Callable[[str],None]]=None,

        headless:bool=True,

        additional_data:Optional[dict]=None,
        **kwargs
    )->Optional[QThread]:

        # set objective and well plate type from machine config (or.. should be part of imaging configuration..?)
        # set wells to be imaged <- acquire.well_list argument
        # set grid per well to be imaged
        # set lighting settings per channel
        # set selection and order of channels to be imaged <- acquire.channels argument

        # calculate physical imaging positions on wellplate given plate type and well selection
        plate_type=config.plate_type
        wellplate_format=WELLPLATE_FORMATS[plate_type]

        # validate well positions (should be on the plate, given selected wellplate type)
        if wellplate_format.number_of_skip>0:
            for well_row,well_column in config.well_list:
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

        well_list_names:List[str]=[wellplate_format.well_name(*c) for c in config.well_list]
        well_list_physical_pos:List[Tuple[float,float]]=[wellplate_format.convert_well_index(*c) for c in config.well_list]

        # print well names as debug info
        #print("imaging wells: ",", ".join(well_list_names))

        # set autofocus parameters
        if config.af_software_channel is None:
            self.multipointController.set_software_af_flag(False)
        else:
            assert config.af_software_channel in [c.name for c in self.configurationManager.configurations], f"{config.af_software_channel} is not a valid (AF) channel"
            if config.af_software_channel!=MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL:
                MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL=config.af_software_channel
            self.multipointController.set_software_af_flag(True)

        self.multipointController.set_laser_af_flag(config.af_laser_on)

        # set grid data per well
        self.set_NX(config.grid_config.x.N)
        self.set_NY(config.grid_config.y.N)
        self.set_NZ(config.grid_config.z.N)
        self.set_Nt(config.grid_config.t.N)
        self.set_deltaX(config.grid_config.x.d)
        self.set_deltaY(config.grid_config.y.d)
        self.set_deltaZ(config.grid_config.z.d)
        self.set_deltat(config.grid_config.t.d)

        for i,(well_row,well_column) in enumerate(config.well_list):
            well_x_mm,well_y_mm=well_list_physical_pos[i]
            for x_grid_item,y_grid_item in self.multipointController.grid_positions_for_well(well_x_mm,well_y_mm):
                if self.fov_exceeds_well_boundary(well_row,well_column,x_grid_item,y_grid_item):
                    raise ValueError(f"at least one grid item is outside the bounds of the well! well size is {wellplate_format.well_size_mm}mm")

        # set list of imaging channels
        self.set_selected_configurations(config.channels_ordered)

        # set image saving location
        acquisition_data=config.as_json(well_index_to_name=True)
        acquisition_data.update(additional_data)
        self.multipointController.prepare_folder_for_new_experiment(output_path=config.output_path,complete_experiment_data=acquisition_data) # todo change this to a callback (so that each image can be handled in a callback, not as batch or whatever)

        # start experiment, and return thread that actually does the imaging (thread.finished can be connected to some callback)
        return self.multipointController.run_experiment(
            well_selection = ( well_list_names, well_list_physical_pos ),
            grid_mask = config.grid_mask,

            set_num_acquisitions_callback = set_num_acquisitions_callback,
            on_new_acquisition = on_new_acquisition,

            headless = headless,
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

    
