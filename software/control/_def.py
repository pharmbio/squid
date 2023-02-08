from dataclasses import dataclass, field
import json
from pathlib import Path
from enum import Enum

from typing import Optional, Dict, List, ClassVar, Any, Tuple, Union

from control.typechecker import TypecheckClass, ClosedRange, ClosedSet, TypecheckFunction
#from control.core import Configuration
from qtpy.QtCore import Signal, QObject

import control.gxipy as gx
import numpy

class AcquisitionImageData:
    image:numpy.ndarray
    path:str
    config:"Configuration"
    x:Optional[int]
    y:Optional[int]
    z:Optional[int]
    well_name:Optional[str]

    def __init__(self,
        image:numpy.ndarray,
        path:str,
        config:"Configuration",
        x:Optional[int]=None,
        y:Optional[int]=None,
        z:Optional[int]=None,
        well_name:Optional[str]=None,
    ):
        self.image=image
        self.path=path
        self.config=config
        self.x=x
        self.y=y
        self.z=z
        self.well_name=well_name

class AcquisitionStartResultType(str,Enum):
    Done="done"
    RaisedException="exception"
    Async="async"
    Dry="dry"

class AcquisitionStartResult:
    acquisition_config:"AcquisitionConfig"
    type:AcquisitionStartResultType
    exception:Optional[Exception]
    async_signal_on_finish:Optional[Signal]

    def __init__(self,
        acquisition_config:"AcquisitionConfig",
        type:Union[None,AcquisitionStartResultType,str]=None,
        exception:Optional[Exception]=None,
        async_signal_on_finish:Optional[Signal]=None,
    ):
        self.acquisition_config=acquisition_config
        self.exception=None
        self.async_signal_on_finish=None

        if not type is None and type in (AcquisitionStartResultType.Dry,AcquisitionStartResultType.Dry.value):
            self.type=AcquisitionStartResultType.Dry
            return

        if not exception is None:
            assert type in (None,"exception",AcquisitionStartResultType.RaisedException)
            assert async_signal_on_finish is None
            self.type=AcquisitionStartResultType.RaisedException
            self.exception=exception
        if not async_signal_on_finish is None:
            assert type in (None,"async",AcquisitionStartResultType.Async)
            assert exception is None
            self.type=AcquisitionStartResultType.Async
            self.async_signal_on_finish=async_signal_on_finish

        if not type is None:
            if isinstance(type,AcquisitionStartResultType):
                self.type=type
            else: # is str
                self.type=AcquisitionStartResultType(type)
        else:
            _=self.type # make sure that self.type has been set        

class AcqusitionProgress:
    total_steps:int
    completed_steps:int
    start_time:float
    last_imaged_coordinates:Tuple[float,float]
    last_step_completion_time:float
    _last_completed_action:str

    def __init__(self,
        total_steps:int,
        completed_steps:int,
        start_time:float,
        last_imaged_coordinates:Tuple[float,float],
        last_step_completion_time:float=float("nan"),
    ):
        self.total_steps=total_steps
        self.completed_steps=completed_steps
        self.start_time=start_time
        self.last_imaged_coordinates=last_imaged_coordinates
        self.last_step_completion_time=last_step_completion_time

    @property
    def last_completed_action(self)->float:
        return self._last_completed_action
    
    @last_completed_action.setter
    def last_completed_action(self,new_last_action:str):
        self._last_completed_action=new_last_action
        self.last_step_completion_time=time.time()

class TriggerMode(str,Enum):
    SOFTWARE = 'Software'
    HARDWARE = 'Hardware'

class ImageFormat(Enum):
    BMP=0
    TIFF=1
    TIFF_COMPRESSED=2

@TypecheckClass(create_str=True)
class CameraPixelFormat:
    name:str
    num_bytes_per_pixel:int
    gx_pixel_format:Union[gx.GxPixelFormatEntry,int] # instances of gx.GxPixelFormatEntry are represented as an int

import time

class Profiler:
    def __init__(self,msg:str,parent:Optional["Self"]=None,discard_if_parent_none:bool=True):
        self.msg=msg
        self.parent=parent
        self.discard_if_parent_none=discard_if_parent_none

        if (not self.parent is None) and (self.msg in self.parent.named_children):
            self.duration=self.parent.named_children[self.msg].duration
            self.named_children=self.parent.named_children[self.msg].named_children

        else:
            self.duration=0.0
            self.named_children=dict()

        self.start_time=0.0
    def __enter__(self)->"Self":
        self.start_time=time.monotonic()
        return self
    def __exit__(self,*args,**kwargs):
        self.duration+=time.monotonic()-self.start_time
        if self.parent is None:
            if not self.discard_if_parent_none:
                print( \
                    "------------------ profiling results -----------------\n"
                    f"{self.to_text(indent=0,of_total=self.duration)}"
                    "------------------------------------------------------\n"
                )
        else:
            self.parent.named_children[self.msg]=self

    def to_text(self,indent:int,of_total:float)->str:
        text=f"{' '*indent} ({(self.duration/of_total*100):6.2f}%) {self.duration:10.3f} : {self.msg}\n"
        for child in self.named_children.values():
            text+=child.to_text(indent=indent+2,of_total=of_total)

        return text

class CAMERA_PIXEL_FORMATS(Enum):
    MONO8=CameraPixelFormat(
        name='Mono8',
        num_bytes_per_pixel=1,
        gx_pixel_format=gx.GxPixelFormatEntry.MONO8,
    )
    MONO10=CameraPixelFormat(
        name='Mono10',
        num_bytes_per_pixel=2,
        gx_pixel_format=gx.GxPixelFormatEntry.MONO10,
    )
    MONO12=CameraPixelFormat(
        name='Mono12',
        num_bytes_per_pixel=2,
        gx_pixel_format=gx.GxPixelFormatEntry.MONO12,
    )
    MONO14=CameraPixelFormat(
        name='Mono14',
        num_bytes_per_pixel=2,
        gx_pixel_format=gx.GxPixelFormatEntry.MONO14,
    )
    MONO16=CameraPixelFormat(
        name='Mono16',
        num_bytes_per_pixel=2,
        gx_pixel_format=gx.GxPixelFormatEntry.MONO16,
    )
    BAYER_RG8=CameraPixelFormat(
        name='BAYER_RG8',
        num_bytes_per_pixel=1,
        gx_pixel_format=gx.GxPixelFormatEntry.BAYER_RG8,
    )
    BAYER_RG12=CameraPixelFormat(
        name='BAYER_RG12',
        num_bytes_per_pixel=2,
        gx_pixel_format=gx.GxPixelFormatEntry.BAYER_RG12,
    )


class Acquisition:
    """ config stuff for (multi point) image acquisition """
    
    CROP_WIDTH:int = 3000
    """ crop width for images after recording from camera sensor """
    CROP_HEIGHT:int = 3000
    """ crop height for images after recording from camera sensor """
    NUMBER_OF_FOVS_PER_AF:int = 3
    IMAGE_FORMAT:ImageFormat = ImageFormat.TIFF
    """ file format used for images saved after multi point image acquisition """
    IMAGE_DISPLAY_SCALING_FACTOR:ClosedRange[float](0.0,1.0) = 1.0
    """ this _crops_ the image display for the multi point acquisition """

class DefaultMultiPointGrid:
    """ multi point grid defaults """

    DEFAULT_Nx:int = 1
    DEFAULT_Ny:int = 1
    DEFAULT_Nz:int = 1
    DEFAULT_Nt:int = 1

    DEFAULT_DX_MM:float = 0.9
    DEFAULT_DY_MM:float = 0.9
    DEFAULT_DZ_MM:float = 1.5e-3
    DEFAULT_DT_S:float = 1.0

class PosUpdate:
    INTERVAL_MS = 25

class MicrocontrollerDef:
    MSG_LENGTH = 24
    CMD_LENGTH = 8
    N_BYTES_POS = 4

class MCU_PINS:
    PWM1 = 5
    PWM2 = 4
    PWM3 = 22
    PWM4 = 3
    PWM5 = 23
    PWM6 = 2
    PWM7 = 1
    PWM9 = 6
    PWM10 = 7
    PWM11 = 8
    PWM12 = 9
    PWM13 = 10
    PWM14 = 15
    PWM15 = 24
    PWM16 = 25
    AF_LASER = 15

class CMD_SET:
    MOVE_X = 0
    MOVE_Y = 1
    MOVE_Z = 2
    MOVE_THETA = 3
    HOME_OR_ZERO = 5
    TURN_ON_ILLUMINATION = 10
    TURN_OFF_ILLUMINATION = 11
    SET_ILLUMINATION = 12
    SET_ILLUMINATION_LED_MATRIX = 13
    ACK_JOYSTICK_BUTTON_PRESSED = 14
    ANALOG_WRITE_ONBOARD_DAC = 15
    MOVETO_X = 6
    MOVETO_Y = 7
    MOVETO_Z = 8
    SET_LIM = 9
    SET_LIM_SWITCH_POLARITY = 20
    CONFIGURE_STEPPER_DRIVER = 21
    SET_MAX_VELOCITY_ACCELERATION = 22
    SET_LEAD_SCREW_PITCH = 23
    SET_OFFSET_VELOCITY = 24
    SEND_HARDWARE_TRIGGER = 30
    SET_STROBE_DELAY = 31
    SET_PIN_LEVEL = 41
    INITIALIZE = 254
    RESET = 255

class CMD_SET2: # enum
    ANALOG_WRITE_DAC8050X:int = 0
    SET_CAMERA_TRIGGER_FREQUENCY:int = 1
    START_CAMERA_TRIGGERING:int = 2
    STOP_CAMERA_TRIGGERING:int = 3

BIT_POS_JOYSTICK_BUTTON = 0
BIT_POS_SWITCH = 1

class HOME_OR_ZERO: # enum
    HOME_NEGATIVE:int = 1 # motor moves along the negative direction (MCU coordinates)
    HOME_POSITIVE:int = 0 # motor moves along the negative direction (MCU coordinates)
    ZERO:int = 2

class AXIS:
    X:int = 0
    Y:int = 1
    Z:int = 2
    THETA:int = 3
    XY:int = 4

class LIMIT_CODE:
    X_POSITIVE:int = 0
    X_NEGATIVE:int = 1
    Y_POSITIVE:int = 2
    Y_NEGATIVE:int = 3
    Z_POSITIVE:int = 4
    Z_NEGATIVE:int = 5

class LIMIT_SWITCH_POLARITY: # enum
    ACTIVE_LOW:int = 0
    ACTIVE_HIGH:int = 1
    DISABLED:int = 2

class ILLUMINATION_CODE: # enum
    ILLUMINATION_SOURCE_LED_ARRAY_FULL:int = 0
    ILLUMINATION_SOURCE_LED_ARRAY_LEFT_HALF:int = 1
    ILLUMINATION_SOURCE_LED_ARRAY_RIGHT_HALF:int = 2
    ILLUMINATION_SOURCE_LED_ARRAY_LEFTB_RIGHTR:int = 3
    ILLUMINATION_SOURCE_LED_ARRAY_LOW_NA:int = 4
    ILLUMINATION_SOURCE_LED_ARRAY_LEFT_DOT:int = 5
    ILLUMINATION_SOURCE_LED_ARRAY_RIGHT_DOT:int = 6
    ILLUMINATION_SOURCE_LED_EXTERNAL_FET:int = 20
    ILLUMINATION_SOURCE_405NM:int = 11
    ILLUMINATION_SOURCE_488NM:int = 12
    ILLUMINATION_SOURCE_638NM:int = 13
    ILLUMINATION_SOURCE_561NM:int = 14
    ILLUMINATION_SOURCE_730NM:int = 15

class CAMERA:
    ROI_OFFSET_X_DEFAULT:int = 0
    ROI_OFFSET_Y_DEFAULT:int = 0
    ROI_WIDTH_DEFAULT:int = 3000
    ROI_HEIGHT_DEFAULT:int = 3000

class VOLUMETRIC_IMAGING:
    NUM_PLANES_PER_VOLUME:int = 20

class CMD_EXECUTION_STATUS: # enum
    COMPLETED_WITHOUT_ERRORS:int = 0
    IN_PROGRESS:int = 1
    CMD_CHECKSUM_ERROR:int = 2
    CMD_INVALID:int = 3
    CMD_EXECUTION_ERROR:int = 4
    ERROR_CODE_EMPTYING_THE_FLUDIIC_LINE_FAILED:int = 100

@dataclass(frozen=True)
class AutofocusConfig:
    STOP_THRESHOLD:float = 0.85
    CROP_WIDTH:int = 800
    CROP_HEIGHT:int = 800


@dataclass(frozen=True)
class WellplateFormatPhysical:
    """ physical characteristics of a wellplate type """

    well_size_mm:float # diameter
    """ physical (and logical) well plate layout """

    well_spacing_mm:float # mm from top left of one well to top left of next well (same in both axis)

    A1_x_mm:float
    A1_y_mm:float

    number_of_skip:int
    """ layers of disabled outer wells """

    rows:int
    columns:int

    def imageable_origin(self)->Tuple[float,float]:
        """
        
        offset for coordinate origin, based on calibration with 384 wellplate

        returns x,y coordinate in mm of imageable origin, i.e. top left coordinate of top-left well (does NOT mean that the corner can actualle be imaged, i.e. the well containing that corner may not be valid.)
        this should only be used for internal reference
        
        """

        wellplate_format_384=WELLPLATE_FORMATS[384]

        # explanation for math below:
        #   A1 coordinates for wellplate type are coordinates for center of well A1, so offset half the well size towards top left for origin
        #   position calibration is done via a 384 wellplate, so:
        #       take calibrated position (MACHINE_CONFIG.{X,Y}_MM_384_WELLPLATE_UPPERLEFT), which is the top left corner of well B2
        #       so subtract well spacing once (B2 -> A1)
        #       and add half the well size to move to center of A1 (i.e. now we have calibrated coordinates of center of A1 on 384 wellplate)
        #       then subtract the expected center of A1
        #           -> now we have calibrated offset for coordinates of center of well A1
        #       then add offset to center of A1 of current plate type


        origin_x_mm = self.A1_x_mm - self.well_size_mm/2 + \
            MACHINE_CONFIG.X_MM_384_WELLPLATE_UPPERLEFT + wellplate_format_384.well_size_mm/2 - \
            (wellplate_format_384.A1_x_mm + wellplate_format_384.well_spacing_mm )
        
        origin_y_mm = self.A1_y_mm - self.well_size_mm/2 + \
            MACHINE_CONFIG.Y_MM_384_WELLPLATE_UPPERLEFT + wellplate_format_384.well_size_mm/2 - \
            (wellplate_format_384.A1_y_mm + wellplate_format_384.well_spacing_mm )

        return (
            origin_x_mm,
            origin_y_mm
        )

    @TypecheckFunction
    def well_index_to_mm(self,row:int,column:int)->Tuple[float,float]:
        origin_x_offset,origin_y_offset=self.imageable_origin()

        # physical position of the well on the wellplate that the cursor should move to
        well_on_plate_offset_x=column * self.well_spacing_mm
        well_on_plate_offset_y=row * self.well_spacing_mm

        # offset from top left of well to position within well where cursor/camera should go
        # should be centered, so offset is same in x and y
        well_cursor_offset_x=self.well_size_mm/2
        well_cursor_offset_y=self.well_size_mm/2

        x_mm = origin_x_offset + well_on_plate_offset_x + well_cursor_offset_x
        y_mm = origin_y_offset + well_on_plate_offset_y + well_cursor_offset_y

        return (x_mm,y_mm)

    @TypecheckFunction
    def well_index_to_name(self,row:int,column:int,check_valid:bool=True)->str:
        if check_valid:
            assert row>=(0+self.number_of_skip) and row<=(self.rows-self.number_of_skip-1), f"{row=} {column=}"
            assert column>=(0+self.number_of_skip) and column<=(self.columns-self.number_of_skip-1), f"{row=} {column=}"

        well_name=chr(ord('A')+row)+f'{column+1:02}' # e.g. A01
        return well_name

    @TypecheckFunction
    def well_name_to_index(self,name:str,check_valid:bool=True)->Tuple[int,int]:
        assert len(name)==3, name # first character must be letter denoting the row, second and third character must be integer representing the column index (the latter starting at 1, not 0, and single digit numbers must be preceded by a 0)

        row=ord(name[0])-ord('A')
        column=int(name[1:])-1 # because column numbering starts at 1, but indices start at 0

        if check_valid:
            assert row>=(0+self.number_of_skip) and row<=(self.rows-self.number_of_skip-1), name
            assert column>=(0+self.number_of_skip) and column<=(self.columns-self.number_of_skip-1), name

        return row,column

    @TypecheckFunction
    def is_well_reachable(self,row:int,column:int,allow_corners:bool=False)->bool:
        row_lower_bound=0 + self.number_of_skip
        row_upper_bound=self.rows-1-self.number_of_skip
        column_lower_bound=0 + self.number_of_skip
        column_upper_bound=self.columns-1-self.number_of_skip

        well_reachable=(row >= row_lower_bound and row <= row_upper_bound ) and ( column >= column_lower_bound and column <= column_upper_bound )
        
        if not allow_corners:
            is_in_top_left_corner     = ( row == row_lower_bound ) and ( column == column_lower_bound )
            is_in_bottom_left_corner  = ( row == row_upper_bound ) and ( column == column_lower_bound )
            is_in_top_right_corner    = ( row == row_lower_bound ) and ( column == column_upper_bound )
            is_in_bottom_right_corner = ( row == row_upper_bound ) and ( column == column_upper_bound )

            well_reachable=well_reachable and not (is_in_top_left_corner or is_in_bottom_left_corner or is_in_top_right_corner or is_in_bottom_right_corner)

        return well_reachable

    @TypecheckFunction
    def row_has_invalid_wells(self,row:int)->bool:
        """
        this function is used to check for invalid wells within the generally reachable area, so wells within the outer skip area are ignored here!
        """
        for c in range(self.columns):
            if not self.is_well_reachable(row=row,column=c,allow_corners=False and self.number_of_skip==0 and self.columns==24):
                return True

        return False

    @TypecheckFunction
    def column_has_invalid_wells(self,column:int)->bool:
        """
        this function is used to check for invalid wells within the generally reachable area, so wells within the outer skip area are ignored here!
        """
        for r in range(self.rows):
            if not self.is_well_reachable(row=r,column=column,allow_corners=False and self.number_of_skip==0 and self.columns==24):
                return True

        return False
    
    def pos_mm_to_well_index(self,x_mm:float,y_mm:float,return_nearest_valid_well_instead_of_none_if_outside:bool=False)->Optional[Tuple[int,int]]:
        origin_x,origin_y=self.imageable_origin()
        if x_mm>=origin_x and y_mm>=origin_y:
            x_mm-=origin_x
            y_mm-=origin_y

            x_wells=int(x_mm//self.well_spacing_mm)
            y_wells=int(y_mm//self.well_spacing_mm)

            x_well_edge_distance=x_mm%self.well_spacing_mm
            y_well_edge_distance=y_mm%self.well_spacing_mm

            if return_nearest_valid_well_instead_of_none_if_outside:
                raise ValueError("unimplemented")

            if x_well_edge_distance<=self.well_size_mm and y_well_edge_distance<=self.well_size_mm:
                row,column=y_wells,x_wells
                pass #print(f"inside well {self.well_index_to_name(row=y_wells,column=x_wells,check_valid=False)} with remaining {x_well_edge_distance=} {y_well_edge_distance=}")
                return row,column

        return None

    def limit_safe(self,calibrated:bool=False)->"SoftwareStagePositionLimits":
        if calibrated:
            return SoftwareStagePositionLimits(
                X_NEGATIVE = 10.0,
                X_POSITIVE = 112.5,
                Y_NEGATIVE = 6.0,
                Y_POSITIVE = 76.0,
                Z_POSITIVE = 6.0,
            )
        else:
            return SoftwareStagePositionLimits(
                X_NEGATIVE = 10.0,
                X_POSITIVE = 112.5,
                Y_NEGATIVE = 6.0,
                Y_POSITIVE = 76.0,
                Z_POSITIVE = 6.0,
            )
    
    def limit_unsafe(self,calibrated:bool=False)->"SoftwareStagePositionLimits":
        physical_wellplate_format=self # WELLPLATE_FORMATS[384]

        if calibrated:
            # these values are manually calibrated to be upper left coordinates of well B2 (instead of A1!)
            x_start_mm = MACHINE_CONFIG.X_MM_384_WELLPLATE_UPPERLEFT
            y_start_mm = MACHINE_CONFIG.Y_MM_384_WELLPLATE_UPPERLEFT

        else:
            weird_factor = 1.0 # a1_y_mm is 9mm from plate CAD info, but y_start_mm defaults to 10mm, which actually works. unsure where this physical offset comes from
            x_start_mm = physical_wellplate_format.A1_x_mm
            y_start_mm = physical_wellplate_format.A1_y_mm + weird_factor

        # adjust plate origin for number_of_skip (and take into account that references above are for upper left corner of well B2 instead of A1, even though upper left of A1 is origin of image-able area)
        x_start_mm=x_start_mm+(physical_wellplate_format.number_of_skip-1)*physical_wellplate_format.well_spacing_mm
        y_start_mm=y_start_mm+(physical_wellplate_format.number_of_skip-1)*physical_wellplate_format.well_spacing_mm

        # taking number_of_skip into account, calculate distance from top left of image-able area to bottom right
        x_end_mm = x_start_mm + (physical_wellplate_format.columns - 1 - physical_wellplate_format.number_of_skip*2) * physical_wellplate_format.well_spacing_mm + physical_wellplate_format.well_size_mm
        y_end_mm = y_start_mm + (physical_wellplate_format.rows - 1 - physical_wellplate_format.number_of_skip*2) * physical_wellplate_format.well_spacing_mm + physical_wellplate_format.well_size_mm

        return SoftwareStagePositionLimits(
            X_NEGATIVE = x_start_mm,
            X_POSITIVE = x_end_mm,
            Y_NEGATIVE = y_start_mm,
            Y_POSITIVE = y_end_mm,

            Z_POSITIVE = 6.0,
        )

    @TypecheckFunction
    def fov_exceeds_well_boundary(self,well_row:int,well_column:int,x_mm:float,y_mm:float)->bool:
        """
        check if a position on the plate exceeds the boundaries of a well
        (plate position in mm relative to plate origin. well position as row and column index, where row A and column 1 have index 0)
        """

        well_center_x_mm,well_center_y_mm=self.well_index_to_mm(well_row,well_column)

        # assuming wells are square (even though they are round-ish)
        well_left_boundary=well_center_x_mm-self.well_size_mm/2
        well_right_boundary=well_center_x_mm+self.well_size_mm/2
        assert well_left_boundary<well_right_boundary
        well_upper_boundary=well_center_y_mm+self.well_size_mm/2
        well_lower_boundary=well_center_y_mm-self.well_size_mm/2
        assert well_lower_boundary<well_upper_boundary

        is_in_bounds=x_mm>=well_left_boundary and x_mm<=well_right_boundary and y_mm<=well_upper_boundary and y_mm>=well_lower_boundary

        return not is_in_bounds

WELLPLATE_FORMATS:Dict[int,WellplateFormatPhysical]={
    6:WellplateFormatPhysical(
        well_size_mm = 34.94,
        well_spacing_mm = 39.2,
        A1_x_mm = 24.55,
        A1_y_mm = 23.01,
        number_of_skip = 0,
        rows = 2,
        columns = 3,
    ),
    12:WellplateFormatPhysical(
        well_size_mm = 22.05,
        well_spacing_mm = 26,
        A1_x_mm = 24.75,
        A1_y_mm = 16.86,
        number_of_skip = 0,
        rows = 3,
        columns = 4,
    ),
    24:WellplateFormatPhysical(
        well_size_mm = 15.54,
        well_spacing_mm = 19.3,
        A1_x_mm = 17.05,
        A1_y_mm = 13.67,
        number_of_skip = 0,
        rows = 4,
        columns = 6,
    ),
    96:WellplateFormatPhysical(
        well_size_mm = 6.21,
        well_spacing_mm = 9,
        A1_x_mm = 14.3,
        A1_y_mm = 11.36,
        number_of_skip = 0,
        rows = 8,
        columns = 12,
    ),
    384:WellplateFormatPhysical(
        well_size_mm = 3.3,
        well_spacing_mm = 4.5,
        A1_x_mm = 12.05,
        A1_y_mm = 9.05,
        number_of_skip = 0,
        rows = 16,
        columns = 24,
    )
}
WELLPLATE_NAMES:Dict[int,str]={
    i:f"{i} well plate"
    for i in WELLPLATE_FORMATS.keys()
}

WELLPLATE_TYPE_IMAGE={
    WELLPLATE_NAMES[384] : 'images/384_well_plate_1509x1010.png',
    WELLPLATE_NAMES[96]  : 'images/96_well_plate_1509x1010.png',
    WELLPLATE_NAMES[24]  : 'images/24_well_plate_1509x1010.png',
    WELLPLATE_NAMES[12]  : 'images/12_well_plate_1509x1010.png',
    WELLPLATE_NAMES[6]   : 'images/6_well_plate_1509x1010.png'
}

assert WELLPLATE_FORMATS[384].well_name_to_index("A01",check_valid=False)==(0,0)
assert WELLPLATE_FORMATS[384].well_name_to_index("B02",check_valid=False)==(1,1)
assert WELLPLATE_FORMATS[384].well_index_to_name(row=0,column=0,check_valid=False)=="A01"
assert WELLPLATE_FORMATS[384].well_index_to_name(row=1,column=1,check_valid=False)=="B02"

@dataclass(frozen=True,repr=True)
class SoftwareStagePositionLimits:
    """ limits in mm from home/loading position"""

    X_POSITIVE:float = 112.5
    X_NEGATIVE:float = 10.0
    Y_POSITIVE:float = 76.0
    Y_NEGATIVE:float = 6.0
    Z_POSITIVE:float = 6.0

    # the following limits that have popped up in other places: (likely used for another stage type)
    #   X_POSITIVE:float = 56
    #   X_NEGATIVE:float = -0.5
    #   Y_POSITIVE:float = 56
    #   Y_NEGATIVE:float = -0.5

class FocusMeasureOperators(str,Enum):
    """ focus measure operators - GLVA has worked well for darkfield/fluorescence, and LAPE has worked well for brightfield """
    GLVA="GLVA"
    LAPE="LAPE"

class ControllerType(str,Enum):
    DUE='Arduino Due'
    TEENSY='Teensy'

class BrightfieldSavingMode(str,Enum):
    RAW='Raw'
    RGB2GRAY='RGB2GRAY'
    GREEN_ONLY='Green Channel Only'

###########################################################
#### machine specific configurations - to be overridden ###
###########################################################

@TypecheckClass(check_assignment=True)
class MutableMachineConfiguration(QObject):
    # things that can change in hardware (manual changes)
    DEFAULT_OBJECTIVE:str = '10x (Mitutoyo)'
    WELLPLATE_FORMAT:ClosedSet[int](6,12,24,96,384) = 96

    # things that can change in software
    DEFAULT_TRIGGER_MODE:TriggerMode = TriggerMode.SOFTWARE
    FOCUS_MEASURE_OPERATOR:FocusMeasureOperators = FocusMeasureOperators.LAPE
    MULTIPOINT_AUTOFOCUS_CHANNEL:str = 'Fluorescence 561 nm Ex'
    MULTIPOINT_BF_SAVING_OPTION:BrightfieldSavingMode = BrightfieldSavingMode.RAW

    objective_change:Signal=Signal(str)
    wellplate_format_change:Signal=Signal(int)
    trigger_mode_change:Signal=Signal(TriggerMode)
    focuse_measure_operator_change:Signal=Signal(FocusMeasureOperators)
    autofocus_channel_change:Signal=Signal(str)
    brightfield_saving_mode_change:Signal=Signal(BrightfieldSavingMode)

    def __setattr__(self,name,value):
        {
            "DEFAULT_OBJECTIVE":self.objective_change,
            "WELLPLATE_FORMAT":self.wellplate_format_change,
            "DEFAULT_TRIGGER_MODE":self.trigger_mode_change,
            "FOCUS_MEASURE_OPERATOR":self.focuse_measure_operator_change,
            "MULTIPOINT_AUTOFOCUS_CHANNEL":self.autofocus_channel_change,
            "MULTIPOINT_BF_SAVING_OPTION":self.brightfield_saving_mode_change,
        }[name].emit(value)
        super().__setattr__(name,value)

    def from_json(json_data:dict):
        return MutableMachineConfiguration(**json_data)

@TypecheckClass
class MachineDisplayConfiguration:
    """ display settings """
    DEFAULT_SAVING_PATH:str = str(Path.home()/"Downloads")
    DEFAULT_DISPLAY_CROP:ClosedRange[int](1,100) = 100
    MULTIPOINT_SOFTWARE_AUTOFOCUS_ENABLE_BY_DEFAULT:bool = False
    SHOW_XY_MOVEMENT:bool = False

    def from_json(json_data:dict):
        return MachineDisplayConfiguration(**json_data)



CAMERA_PIXEL_SIZE_UM:Dict[str,float]={
    'IMX290':    2.9,
    'IMX178':    2.4,
    'IMX226':    1.85,
    'IMX250':    3.45,
    'IMX252':    3.45,
    'IMX273':    3.45,
    'IMX264':    3.45,
    'IMX265':    3.45,
    'IMX571':    3.76,
    'PYTHON300': 4.8
}

@dataclass(frozen=True)
class ObjectiveData:
    magnification:float
    NA:float # numerical aperture
    tube_lens_f_mm:float # tube lens focal length in mm1

OBJECTIVES:Dict[str,ObjectiveData]={
    '2x':ObjectiveData(
        magnification=2,
        NA=0.10,
        tube_lens_f_mm=180
    ),
    '4x':ObjectiveData(
        magnification=4,
        NA=0.13,
        tube_lens_f_mm=180
    ),
    '10x':ObjectiveData(
        magnification=10,
        NA=0.25,
        tube_lens_f_mm=180
    ),
    '10x (Mitutoyo)':ObjectiveData(
        magnification=10,
        NA=0.25,
        tube_lens_f_mm=200
    ),
    '20x (Boli)':ObjectiveData(
        magnification=20,
        NA=0.4,
        tube_lens_f_mm=180
    ),
    '20x (Nikon)':ObjectiveData(
        magnification=20,
        NA=0.45,
        tube_lens_f_mm=200
    ),
    '20x (Olympus)':ObjectiveData( # UPLFLN20X
        magnification=20,
        NA=0.50,
        tube_lens_f_mm=180
    ),
    '40x':ObjectiveData(
        magnification=40,
        NA=0.6,
        tube_lens_f_mm=180
    )
}

@TypecheckClass
class MachineConfiguration:

    # hardware specific stuff
    ROTATE_IMAGE_ANGLE:ClosedSet[int](-90,0,90,180)=0
    
    FLIP_IMAGE:ClosedSet[Optional[str]](None,'Vertical','Horizontal','Both')=None

    # note: XY are the in-plane axes, Z is the focus axis

    # change the following so that "backward" is "backward" - towards the single sided hall effect sensor
    STAGE_MOVEMENT_SIGN_X:int = 1
    STAGE_MOVEMENT_SIGN_Y:int = 1
    STAGE_MOVEMENT_SIGN_Z:int = -1
    STAGE_MOVEMENT_SIGN_THETA:int = 1

    STAGE_POS_SIGN_X:int = STAGE_MOVEMENT_SIGN_X
    STAGE_POS_SIGN_Y:int = STAGE_MOVEMENT_SIGN_Y
    STAGE_POS_SIGN_Z:int = STAGE_MOVEMENT_SIGN_Z
    STAGE_POS_SIGN_THETA:int = STAGE_MOVEMENT_SIGN_THETA

    USE_ENCODER_X:bool = False
    USE_ENCODER_Y:bool = False
    USE_ENCODER_Z:bool = False
    USE_ENCODER_THETA:bool = False

    ENCODER_POS_SIGN_X:int = 1
    ENCODER_POS_SIGN_Y:int = 1
    ENCODER_POS_SIGN_Z:int = 1
    ENCODER_POS_SIGN_THETA:int = 1

    ENCODER_STEP_SIZE_X_MM:float = 100e-6
    ENCODER_STEP_SIZE_Y_MM:float = 100e-6
    ENCODER_STEP_SIZE_Z_MM:float = 100e-6
    ENCODER_STEP_SIZE_THETA:float = 1.0

    FULLSTEPS_PER_REV_X:int = 200
    FULLSTEPS_PER_REV_Y:int = 200
    FULLSTEPS_PER_REV_Z:int = 200
    FULLSTEPS_PER_REV_THETA:int = 200

    # beginning of actuator specific configurations

    SCREW_PITCH_X_MM:float = 2.54
    SCREW_PITCH_Y_MM:float = 2.54
    SCREW_PITCH_Z_MM:float = 0.3 # 0.012*25.4 was written here at some point, not sure why. the motor makes _the_ weird noise during homing when set to the latter term, instead of 0.3

    MICROSTEPPING_DEFAULT_X:int = 256
    MICROSTEPPING_DEFAULT_Y:int = 256
    MICROSTEPPING_DEFAULT_Z:int = 256
    MICROSTEPPING_DEFAULT_THETA:int = 256

    X_MOTOR_RMS_CURRENT_mA:int = 1000
    Y_MOTOR_RMS_CURRENT_mA:int = 1000
    Z_MOTOR_RMS_CURRENT_mA:int = 500

    X_MOTOR_I_HOLD:ClosedRange[float](0.0,1.0) = 0.25
    Y_MOTOR_I_HOLD:ClosedRange[float](0.0,1.0) = 0.25
    Z_MOTOR_I_HOLD:ClosedRange[float](0.0,1.0) = 0.5

    MAX_VELOCITY_X_mm:float = 40.0
    MAX_VELOCITY_Y_mm:float = 40.0
    MAX_VELOCITY_Z_mm:float = 2.0

    MAX_ACCELERATION_X_mm:float = 500.0
    MAX_ACCELERATION_Y_mm:float = 500.0
    MAX_ACCELERATION_Z_mm:float = 100.0

    # end of actuator specific configurations

    SCAN_STABILIZATION_TIME_MS_X:float = 160.0
    SCAN_STABILIZATION_TIME_MS_Y:float = 160.0
    SCAN_STABILIZATION_TIME_MS_Z:float = 20.0

    # limit switch
    X_HOME_SWITCH_POLARITY:int = LIMIT_SWITCH_POLARITY.ACTIVE_HIGH
    Y_HOME_SWITCH_POLARITY:int = LIMIT_SWITCH_POLARITY.ACTIVE_HIGH
    Z_HOME_SWITCH_POLARITY:int = LIMIT_SWITCH_POLARITY.ACTIVE_LOW

    HOMING_ENABLED_X:bool = False
    HOMING_ENABLED_Y:bool = False
    HOMING_ENABLED_Z:bool = False

    SLEEP_TIME_S:float = 0.005

    LED_MATRIX_R_FACTOR:int = 1
    LED_MATRIX_G_FACTOR:int = 1
    LED_MATRIX_B_FACTOR:int = 1

    TUBE_LENS_MM:float = 50.0
    CAMERA_SENSOR:str = 'IMX226'

    TRACKERS:ClassVar[List[str]] = ['csrt', 'kcf', 'mil', 'tld', 'medianflow','mosse','daSiamRPN']
    DEFAULT_TRACKER:ClosedSet[str]('csrt', 'kcf', 'mil', 'tld', 'medianflow','mosse','daSiamRPN') = 'csrt'

    AF:AutofocusConfig=AutofocusConfig()

    SOFTWARE_POS_LIMIT:SoftwareStagePositionLimits=WELLPLATE_FORMATS[MutableMachineConfiguration.WELLPLATE_FORMAT].limit_safe(calibrated=False)

    ENABLE_STROBE_OUTPUT:bool = False

    Z_STACKING_CONFIG:ClosedSet[str]('FROM CENTER', 'FROM BOTTOM', 'FROM TOP') = 'FROM CENTER'

    # for 384 well plate
    X_MM_384_WELLPLATE_UPPERLEFT:float = 0.0 # for well B2 (NOT A1!!)
    Y_MM_384_WELLPLATE_UPPERLEFT:float = 0.0 # for well B2 (NOT A1!!)

    DEFAULT_Z_POS_MM:float = 1.0
    X_ORIGIN_384_WELLPLATE_PIXEL:int = 177 # upper left of B2 (corner opposite from clamp)
    Y_ORIGIN_384_WELLPLATE_PIXEL:int = 141 # upper left of B2 (corner opposite from clamp)
    # B1 upper left corner in pixel: x = 124, y = 141
    # B1 upper left corner in mm: x = 12.13 mm - 3.3 mm/2, y = 8.99 mm + 4.5 mm - 3.3 mm/2
    # B2 upper left corner in pixel: x = 177, y = 141

    CONTROLLER_VERSION:ControllerType = ControllerType.TEENSY

    MAIN_CAMERA_MODEL:str="MER2-1220-32U3M"
    FOCUS_CAMERA_MODEL:str="MER2-630-60U3M"

    FOCUS_CAMERA_EXPOSURE_TIME_MS:float = 2.0
    FOCUS_CAMERA_ANALOG_GAIN:float = 0.0
    LASER_AF_AVERAGING_N_PRECISE:int = 5
    LASER_AF_AVERAGING_N_FAST:int = 2
    LASER_AF_DISPLAY_SPOT_IMAGE:bool = False # display laser af image every time when displacement is measured (even in multi point acquisition mode)
    LASER_AF_CROP_WIDTH:int = 1536
    LASER_AF_CROP_HEIGHT:int = 256
    HAS_TWO_INTERFACES:bool = True
    USE_GLASS_TOP:bool = True # use right dot instead of left
    SHOW_LEGACY_DISPLACEMENT_MEASUREMENT_WINDOWS:bool = False
    LASER_AUTOFOCUS_TARGET_MOVE_THRESHOLD_UM:float = 0.3 # when moving to target, if absolute measured displacement after movement is larger than this value, repeat move to target (repeat max once) - note that the usual um/pixel value is 0.4
    LASER_AUTOFOCUS_MOVEMENT_BOUNDARY_LOWER:float = -170.0 # when moving to target, no matter the measured displacement, move not further away from the current position than this value
    LASER_AUTOFOCUS_MOVEMENT_BOUNDARY_UPPER:float =  170.0 # when moving to target, no matter the measured displacement, move not further away from the current position than this value
    LASER_AUTOFOCUS_MOVEMENT_MAX_REPEATS:int = 3 # when moving, move again max this many times to reach displacement target

    MULTIPOINT_REFLECTION_AUTOFOCUS_ENABLE_BY_DEFAULT:bool = False

    DEFAULT_TRIGGER_FPS:float=5.0

    MACHINE_NAME:str="unknown HCS SQUID"

    MUTABLE_STATE:MutableMachineConfiguration
    DISPLAY:MachineDisplayConfiguration

    def from_file(filename:str)->"MachineConfiguration":
        try:
            with open(filename,"r",encoding="utf-8") as json_file:
                kwargs=json.decoder.JSONDecoder().decode(json_file.read())

        except FileNotFoundError:
            kwargs={}

        if 'MUTABLE_STATE' in kwargs:
            mutable_state=MutableMachineConfiguration.from_json(kwargs['MUTABLE_STATE'])
            kwargs['MUTABLE_STATE']=mutable_state
        if 'DISPLAY' in kwargs:
            display=MachineDisplayConfiguration.from_json(kwargs['DISPLAY'])
            kwargs['DISPLAY']=display

        return MachineConfiguration(**kwargs)

SOFTWARE_NAME="SQUID - HCS Microscope Control Software"

MACHINE_CONFIG=MachineConfiguration.from_file("machine_config.json")

#print(f"  safe uncalibrated: {WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT].limit_safe(calibrated=False)}")
#print(f"  safe   calibrated: {WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT].limit_safe(calibrated=True)}")
#print(f"unsafe uncalibrated: {WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT].limit_unsafe(calibrated=False)}")
#print(f"unsafe   calibrated: {WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT].limit_unsafe(calibrated=True)}")

MACHINE_CONFIG.SOFTWARE_POS_LIMIT = WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT].limit_unsafe(calibrated=True)
