# set QT_API environment variable
import os 
os.environ["QT_API"] = "pyqt5"

from datetime import datetime

from control._def import *
from control.typechecker import TypecheckFunction, TypecheckClass
from .configuration import Configuration, ConfigurationManager

from typing import List, Tuple, Callable, Optional

from pathlib import Path

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
    mask:numpy.ndarray

    def as_json(self)->dict:
        return {
            "x":self.x.as_json(),
            "y":self.y.as_json(),
            "z":self.z.as_json(),
            "t":self.t.as_json(),
            "mask":self.mask.tolist()
        }

    def from_json(s:dict)->"WellGridConfig":
        return WellGridConfig(
            x=GridDimensionConfig.from_json(s["x"]),
            y=GridDimensionConfig.from_json(s["y"]),
            z=GridDimensionConfig.from_json(s["z"]),
            t=GridDimensionConfig.from_json(s["t"]),
            mask=numpy.array(s["mask"]),
        )
    
    @TypecheckFunction
    def grid_positions_for_well(self,well_row:int,well_column:int,plate_type:WellplateFormatPhysical)->List[Tuple[float,float]]:
        well_center_x_mm,well_center_y_mm=plate_type.well_index_to_mm(well_row,well_column)

        coords=[]

        base_x=well_center_x_mm-self.x.d*(self.x.N-1)/2
        base_y=well_center_y_mm-self.y.d*(self.y.N-1)/2

        for i in range(self.y.N):
            y=base_y+i*self.y.d
            for j in range(self.x.N):
                x=base_x+j*self.x.d
                
                if self.mask[i,j]:
                    coords.append((x,y))

        return coords

@TypecheckClass
class LaserAutofocusData:
    x_reference:float
    um_per_px:float

    z_um_at_reference:float
    """ z position of objective in um when reference was set """

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

            "z_um_at_reference":self.z_um_at_reference,

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

            z_um_at_reference=s["z_um_at_reference"],

            x_offset=s["x_offset"],
            y_offset=s["y_offset"],
            x_width=s["x_width"],
            y_width=s["y_width"],

            has_two_interfaces=s["has_two_interfaces"],
            use_glass_top=s["use_glass_top"],
        )

DEFAULT_CELL_LINE_STR:str="<unknown>"
DEFAULT_PLATE_TYPE_STR:str="Generic 384"

class ConfigLoadCondition(str,Enum):
    """
    Condition under which a section of the a config file is loaded
        in the given context

    ALWAYS:
        always load the section

    WHEN_EMPTY:
        only load the section when the target section is empty
    
        e.g. only load project name when project name in the 
             software GUI is currently empty.

        This option is treated as 'never' where it does not make sense, 
            like for the channel configurations, which can  never be 
            empty.
    
    NEVER:
        never load the section
    """
    ALWAYS="always"
    WHEN_EMPTY="when empty"
    NEVER="never"

@TypecheckClass
class ConfigLoadConditionSet:
    LOAD_PROJECT_NAME: ConfigLoadCondition = ConfigLoadCondition.WHEN_EMPTY
    LOAD_PLATE_NAME: ConfigLoadCondition = ConfigLoadCondition.WHEN_EMPTY
    LOAD_CELL_LINE: ConfigLoadCondition = ConfigLoadCondition.WHEN_EMPTY

    LOAD_WELL_SELECTION: ConfigLoadCondition = ConfigLoadCondition.WHEN_EMPTY

    LOAD_GRID_CONFIG: ConfigLoadCondition = ConfigLoadCondition.ALWAYS

    #LOAD_CHANNEL_ORDER: ConfigLoadCondition = ConfigLoadCondition.NEVER
    LOAD_CHANNEL_CONFIG: ConfigLoadCondition = ConfigLoadCondition.ALWAYS
    LOAD_CHANNEL_SELECTION: ConfigLoadCondition = ConfigLoadCondition.WHEN_EMPTY

    LOAD_AF_LASER_REFERENCE: ConfigLoadCondition = ConfigLoadCondition.WHEN_EMPTY

    LOAD_TRIGGER_MODE: ConfigLoadCondition = ConfigLoadCondition.ALWAYS
    LOAD_PIXEL_FORMAT: ConfigLoadCondition = ConfigLoadCondition.ALWAYS
    LOAD_IMAGE_FILE_FORMAT: ConfigLoadCondition = ConfigLoadCondition.ALWAYS
    LOAD_PLATE_TYPE: ConfigLoadCondition = ConfigLoadCondition.ALWAYS
    LOAD_OBJECTIVE: ConfigLoadCondition = ConfigLoadCondition.ALWAYS

    def __setattr__(self, __name: str, __value: Any) -> None:
        if ConfigLoadConditionSet.can_be_empty(__name)==False and __value==ConfigLoadCondition.WHEN_EMPTY:
            raise ValueError(f"ConfigLoadConditionSet.{__name} cannot be {__value}")
        
        return super().__setattr__(__name,__value)

    def can_be_empty(field:str)->bool:
        return {
            "LOAD_PROJECT_NAME":True,
            "LOAD_PLATE_NAME":True,
            "LOAD_CELL_LINE":True,
            "LOAD_WELL_SELECTION":True,
            "LOAD_CHANNEL_SELECTION":True,
            "LOAD_AF_LASER_REFERENCE":True,

            "LOAD_GRID_CONFIG":False,
            "LOAD_CHANNEL_CONFIG":False,
            "LOAD_TRIGGER_MODE":False,
            "LOAD_PIXEL_FORMAT":False,
            "LOAD_IMAGE_FILE_FORMAT":False,
            "LOAD_PLATE_TYPE":False,
            "LOAD_OBJECTIVE":False,
        }.get(field)

    def always()->"Self":
        return ConfigLoadConditionSet(
            LOAD_PROJECT_NAME = ConfigLoadCondition.ALWAYS,
            LOAD_PLATE_NAME = ConfigLoadCondition.ALWAYS,
            LOAD_CELL_LINE = ConfigLoadCondition.ALWAYS,
            LOAD_WELL_SELECTION = ConfigLoadCondition.ALWAYS,
            LOAD_GRID_CONFIG = ConfigLoadCondition.ALWAYS,
            LOAD_CHANNEL_CONFIG = ConfigLoadCondition.ALWAYS,
            LOAD_CHANNEL_SELECTION = ConfigLoadCondition.ALWAYS,
            LOAD_AF_LASER_REFERENCE = ConfigLoadCondition.ALWAYS,
            LOAD_TRIGGER_MODE = ConfigLoadCondition.ALWAYS,
            LOAD_PIXEL_FORMAT = ConfigLoadCondition.ALWAYS,
            LOAD_IMAGE_FILE_FORMAT = ConfigLoadCondition.ALWAYS,
            LOAD_PLATE_TYPE = ConfigLoadCondition.ALWAYS,
            LOAD_OBJECTIVE = ConfigLoadCondition.ALWAYS,
        )

@TypecheckClass
class AcquisitionConfig:
    output_path:str
    project_name:str
    plate_name:str
    cell_line: str # possibly responsible for lighing settings incl. channel-specific z offsets

    well_list:List[Tuple[int,int]]

    grid_config:WellGridConfig

    af_software_channel:Optional[str]=None
    af_laser_on:bool
    af_laser_reference:Optional[LaserAutofocusData]=None

    trigger_mode:TriggerMode
    pixel_format:str
    plate_type:str # e.g. multiple options for 384 from different manufacturers

    channels_ordered:List[str]
    channels_config:List[Configuration]

    image_file_format:ImageFormat

    objective:str = ""
    timestamp:str = ""

    def from_json(file_path:Union[str,Path])->"AcquisitionConfig":
        with open(str(file_path),mode="r",encoding="utf-8") as json_file:
            data=json.decoder.JSONDecoder().decode(json_file.read())

        plate_type= data["plate_type"] if "plate_type" in data else DEFAULT_PLATE_TYPE_STR
        timestamp = data["timestamp"]  if "timestamp"  in data else ""
        objective = data["objective"]  if "objective"  in data else ""

        well_list=data["well_list"]
        for i in range(len(well_list)):
            well=well_list[i]

            if isinstance(well,str):
                physical_plate_format=WELLPLATE_FORMATS[plate_type]
                row,column=physical_plate_format.well_name_to_index(well)
            else:
                row,column=well

            well_list[i]=(row,column)

        af_laser_reference=None
        if "af_laser_reference" in data and not data["af_laser_reference"] is None:
            af_laser_reference=LaserAutofocusData.from_json(data["af_laser_reference"])

        config=AcquisitionConfig(
            output_path=data["output_path"],
            project_name=data["project_name"],
            plate_name=data["plate_name"],
            cell_line=data["cell_line"] if "cell_line" in data else DEFAULT_CELL_LINE_STR,

            well_list=well_list,

            grid_config=WellGridConfig.from_json(data["grid_config"]),

            af_software_channel=data["af_software_channel"],
            af_laser_on=data["af_laser_on"],
            af_laser_reference=af_laser_reference,

            trigger_mode=TriggerMode(data["trigger_mode"]),
            pixel_format=data["pixel_format"],
            plate_type=plate_type,

            channels_ordered=data["channels_ordered"],
            channels_config=[Configuration.from_json(config_dict) for config_dict in data["channels_config"]],

            image_file_format=[image_format for image_format in ImageFormat if image_format.name==data["image_file_format"]][0],

            timestamp=timestamp,
            objective=objective,
        )

        return config

    def as_json(self,well_index_to_name:bool=False)->dict:
        well_list=self.well_list
        if well_index_to_name:
            physical_plate_format=WELLPLATE_FORMATS[self.plate_type]
            well_list=[physical_plate_format.well_index_to_name(w_row,w_column) for w_row,w_column in well_list] # column+1 because on the wellplates the column indices start at 1 (while in code they start at 0)

        return {
            "output_path":self.output_path,
            "project_name":self.project_name,
            "plate_name":self.plate_name,
            "cell_line":self.cell_line,

            "image_file_format":self.image_file_format.name,
            "trigger_mode":self.trigger_mode,
            "pixel_format":self.pixel_format,
            "plate_type":self.plate_type,

            "timestamp":self.timestamp,
            "objective":self.objective,

            "af_software_channel":self.af_software_channel,
            "af_laser_on":self.af_laser_on,
            "af_laser_reference":self.af_laser_reference.as_json() if not self.af_laser_reference is None else None,

            "grid_config":self.grid_config.as_json(),
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

class StreamingCamera:
    def __init__(self,camera):
        self.camera=camera

    def __enter__(self):
        if not self.camera.in_a_state_to_be_used_directly:
            self.was_streaming=self.camera.is_streaming
            self.was_live=self.camera.is_live
            self.callback_was_enabled=self.camera.callback_is_enabled

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
            if not self.was_live:
                self.camera.is_live=False
            if not self.was_streaming:
                self.camera.stop_streaming()

            self.camera.in_a_state_to_be_used_directly=False

class CameraWrapper:
    def __init__(self,
        core_,
        camera,
        filename:str, # file backing up the configurations on disk
        microcontroller,
        use_streamhandler:bool=True, # use streamhandler by default to handle images

        **kwargs
    ):
        self.core=core_
        self.camera=camera
        self.microcontroller=microcontroller

        self.configuration_manager=core.ConfigurationManager(filename=filename)
        if use_streamhandler:
            self.stream_handler=core.StreamHandler()
        else:
            self.stream_handler=None

        self.live_controller=core.LiveController(
            self.core,
            self.camera,self.microcontroller,self.configuration_manager,
            stream_handler=self.stream_handler,
            **kwargs
        )

        self.camera.set_software_triggered_acquisition() # default trigger type

        try:
            _=self.camera.wrapper
            camera_had_wrapper_before=True
        except:
            camera_had_wrapper_before=False

        if not camera_had_wrapper_before:
            self.camera.wrapper=self
        else:
            assert False, "a camera that already had a wrapper was attempted to be put inside a wrapper again"

    def ensure_streaming(self)->StreamingCamera:
        return StreamingCamera(self.camera)
        
    @property
    def pixel_formats(self)->List[str]:
        return list(self.camera.camera.PixelFormat.get_range().keys())

    def close(self):
        self.camera.close()

class Core(QObject):
    @property
    def camera(self):
        return self.main_camera.camera
    @property
    def streamHandler(self):
        return self.main_camera.stream_handler
    @property
    def liveController(self):
        return self.main_camera.live_controller

    @property
    def streamHandler_focus_camera(self):
        return self.focus_camera.stream_handler
    @property
    def liveController_focus_camera(self):
        return self.focus_camera.live_controller

    microcontroller:microcontroller.Microcontroller
    main_camera:CameraWrapper
    focus_camera:CameraWrapper
    navigation:NavigationController
    autofocusController:AutoFocusController
    displacementMeasurementController:Optional[DisplacementMeasurementController]
    laserAutofocusController:Optional[LaserAutofocusController]
    multipointController:MultiPointController
    imageSaver:ImageSaver
    home_on_startup:bool
    num_running_experiments:int

    last_known_pos_x_mm:Optional[float]
    last_known_pos_y_mm:Optional[float]
    last_known_pos_well_row:Optional[int]
    last_known_pos_well_column:Optional[int]

    def __init__(self,home:bool=True,debug_camera_timings:bool=False):
        super().__init__()

        if not home:
            MAIN_LOG.log("warning: disabled homing on startup can lead to misalignment of the stage. proceed at your own risk. (may damage objective, and/or run into software stage position limits, which can lead to unexpected behaviour)")

        # load objects
        try:
            main_camera = camera.Camera(model=MACHINE_CONFIG.MAIN_CAMERA_MODEL,rotate_image_angle=MACHINE_CONFIG.ROTATE_IMAGE_ANGLE,flip_image=MACHINE_CONFIG.FLIP_IMAGE)
            main_camera.open()

            if debug_camera_timings:
                for i in range(0,10):
                    start_time=time.time()
                    main_camera.send_trigger()
                    _image=main_camera.read_frame(10.0)
                    print(f"recorded image {i} of main camera after {time.time()-start_time:.3f}s")

        except Exception as e:
            MAIN_LOG.log('! imaging camera not detected !')
            raise e

        try:
            focus_camera = camera.Camera(model=MACHINE_CONFIG.FOCUS_CAMERA_MODEL,used_for_laser_autofocus=True)
            focus_camera.open()

            if debug_camera_timings:
                for i in range(0,10):
                    start_time=time.time()
                    focus_camera.send_trigger()
                    _image=focus_camera.read_frame(10.0)
                    print(f"recorded image {i} of focus camera after {time.time()-start_time:.3f}s")

        except Exception as e:
            MAIN_LOG.log('! laser AF camera not detected !')
            raise e

        try:
            self.microcontroller:microcontroller.Microcontroller = microcontroller.Microcontroller(version=MACHINE_CONFIG.CONTROLLER_VERSION)
        except Exception as e:
            MAIN_LOG.log("! microcontroller not detected !")
            raise e

        # reset the MCU
        self.microcontroller.reset()
        # reinitialize motor drivers and DAC (in particular for V2.1 driver board where PG is not functional)
        self.microcontroller.initialize_drivers()
        self.microcontroller.configure_actuators()

        self.main_camera=CameraWrapper(
            self,
            camera=main_camera,
            filename='./channel_config_main_camera.json',
            microcontroller=self.microcontroller,
            use_streamhandler=True,
        )
        MACHINE_CONFIG.MUTABLE_STATE.trigger_mode_change.connect(lambda new_trigger_mode:self.main_camera.live_controller.set_trigger_mode(new_trigger_mode))

        self.focus_camera=CameraWrapper(
            self,
            camera=focus_camera,
            filename='./channel_config_focus_camera.json',
            microcontroller=self.microcontroller,
            use_streamhandler=True,

            control_illumination=True,
            for_displacement_measurement=True,
        )

        self.navigation:          core.NavigationController = core.NavigationController(self.microcontroller)
        self.autofocusController: core.AutoFocusController  = core.AutoFocusController(self.camera,self.navigation,self.liveController)

        LASER_AF_ENABLED=True
        if LASER_AF_ENABLED:
            self.displacementMeasurementController = DisplacementMeasurementController()
            self.laserAutofocusController          = core.LaserAutofocusController(
                                                        self.microcontroller,
                                                        self.focus_camera.camera,
                                                        self.liveController_focus_camera,
                                                        self.navigation,
                                                        has_two_interfaces=MACHINE_CONFIG.HAS_TWO_INTERFACES,
                                                        use_glass_top=MACHINE_CONFIG.USE_GLASS_TOP
                                                    )
        else:
            self.displacementMeasurementController=None
            self.laserAutofocusController=None

        self.imageSaver:           core.ImageSaver           = core.ImageSaver()
        self.multipointController: core.MultiPointController = core.MultiPointController(
            self.camera,
            self.navigation,
            self.liveController,
            self.autofocusController,
            self.laserAutofocusController,
            configuration_manager = self.main_camera.configuration_manager,
            image_saver = self.imageSaver,
        )

        self.home_on_startup=home
        if home:
            self.navigation.home(home_x=MACHINE_CONFIG.HOMING_ENABLED_X,home_y=MACHINE_CONFIG.HOMING_ENABLED_Y,home_z=MACHINE_CONFIG.HOMING_ENABLED_Z)

        self.num_running_experiments=0

        self.last_known_pos_x_mm=None
        self.last_known_pos_y_mm=None
        self.last_known_pos_well_row=None
        self.last_known_pos_well_column=None

    # borrowed multipointController functions
    @property
    def set_selected_configurations(self):
        return self.multipointController.set_selected_configurations

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
    def turn_on_AF_laser(self):
        return self.microcontroller.turn_on_AF_laser
    @property
    def turn_off_AF_laser(self):
        return self.microcontroller.turn_off_AF_laser

    @property
    def plate_type(self)->int:
        return MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT

    @TypecheckFunction
    def acquire(self,
        config:AcquisitionConfig,

        on_new_acquisition:Optional[Callable[[AcqusitionProgress],None]]=None,

        additional_data:Optional[dict]=None,

        image_return:Optional[Any]=None,
    )->Optional[QThread]:

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

        well_list_names:List[str]=[wellplate_format.well_index_to_name(*c) for c in config.well_list]
        well_list_physical_pos:List[Tuple[float,float]]=[wellplate_format.well_index_to_mm(*c) for c in config.well_list]

        # set autofocus parameters
        self.multipointController.set_software_af_flag(not config.af_software_channel is None)
        if not config.af_software_channel is None:
            assert config.af_software_channel in [c.name for c in self.main_camera.configuration_manager.configurations], f"{config.af_software_channel} is not a valid (AF) channel"
            if config.af_software_channel!=MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL:
                MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL=config.af_software_channel

        self.multipointController.set_laser_af_flag(config.af_laser_on)

        # set grid data per well
        self.multipointController.set_NX(config.grid_config.x.N)
        self.multipointController.set_NY(config.grid_config.y.N)
        self.multipointController.set_NZ(config.grid_config.z.N)
        self.multipointController.set_Nt(config.grid_config.t.N)
        self.multipointController.set_deltaX(config.grid_config.x.d)
        self.multipointController.set_deltaY(config.grid_config.y.d)
        self.multipointController.set_deltaZ(config.grid_config.z.d)
        self.multipointController.set_deltat(config.grid_config.t.d)

        for well_row,well_column in config.well_list:
            for x_grid_item,y_grid_item in config.grid_config.grid_positions_for_well(well_row,well_column,plate_type=wellplate_format):
                if wellplate_format.fov_exceeds_well_boundary(well_row,well_column,x_grid_item,y_grid_item):
                    raise ValueError(f"at least one grid item is outside the bounds of the well! well size is {wellplate_format.well_diameter_mm}mm")

        # set list of imaging channels
        self.set_selected_configurations(config.channels_ordered)

        # set image saving location
        acquisition_data=config.as_json(well_index_to_name=True)
        acquisition_data.update(additional_data)

        self.prepare_folder_for_new_experiment(output_path=config.output_path,complete_experiment_data=acquisition_data ) # todo change this to a callback (so that each image can be handled in a callback, not as batch or whatever)

        # set file format for saved images
        Acquisition.IMAGE_FORMAT=config.image_file_format # not super ergonomic, but currently the image file format is globally specified via this variable

        # start experiment, and return thread that actually does the imaging (thread.finished can be connected to some callback)
        return self.multipointController.run_experiment(
            well_selection = ( well_list_names, well_list_physical_pos ),
            grid_mask = config.grid_config.mask,

            on_new_acquisition = on_new_acquisition,
            image_return=image_return,

            plate_type=config.plate_type,
        )

    @TypecheckFunction
    def prepare_folder_for_new_experiment(self,output_path:str,complete_experiment_data:dict):
        self.output_path = output_path
        self.multipointController.output_path=output_path

        self.recording_start_time = time.time()

        # config : complete set of config used for the experiment
        complete_data_path = Path(output_path) / 'parameters.json'
        complete_data_path.write_text(json.encoder.JSONEncoder(indent=2).encode(complete_experiment_data))

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

    
