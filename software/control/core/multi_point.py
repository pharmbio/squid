# qt libraries
from qtpy.QtCore import QObject, Signal, QThread, Qt # type: ignore
from qtpy.QtWidgets import QApplication

from control._def import *

import os
import time
import cv2

import json
import pandas as pd
import numpy

from typing import Optional, List, Union, Tuple, Callable

import control.camera as camera
from control.core import Configuration, NavigationController, LiveController, AutoFocusController, ConfigurationManager, ImageSaver #, LaserAutofocusController
from control.typechecker import TypecheckFunction

ENABLE_TQDM_STUFF:bool=False
if ENABLE_TQDM_STUFF:
    from tqdm import tqdm
else:
    def tqdm(iter,*args,**kwargs):
        return iter

from pathlib import Path

from control.gui import *

class AbortAcquisitionException(Exception):
    def __init__(self):
        super().__init__()


class MultiPointWorker(QObject):

    finished = Signal()
    image_to_display = Signal(numpy.ndarray)
    spectrum_to_display = Signal(numpy.ndarray)
    image_to_display_multi = Signal(numpy.ndarray,int)
    signal_register_current_fov = Signal(float,float)
    signal_new_acquisition=Signal(AcqusitionProgress)

    def __init__(self,
        multiPointController,
        scan_coordinates:Tuple[List[str],List[Tuple[float,float]]],
        total_num_acquisitions:int,
        is_async:bool=True,
        image_return:Optional[Callable[[Any],None]]=None,
    ):
        super().__init__()
        self.multiPointController:MultiPointController = multiPointController
        self.is_async=is_async

        # copy all (relevant) fields to unlock multipointcontroller on thread start
        self.camera = self.multiPointController.camera
        self.microcontroller = self.multiPointController.microcontroller
        self.navigation = self.multiPointController.navigation
        self.liveController = self.multiPointController.liveController
        self.autofocusController = self.multiPointController.autofocusController
        self.laserAutofocusController = self.multiPointController.laserAutofocusController
        self.configuration_manager = self.multiPointController.configuration_manager
        self.NX = self.multiPointController.NX
        self.NY = self.multiPointController.NY
        self.NZ = self.multiPointController.NZ
        self.Nt = self.multiPointController.Nt
        self.deltaX = self.multiPointController.deltaX
        self.deltaX_usteps = self.multiPointController.deltaX_usteps
        self.deltaY = self.multiPointController.deltaY
        self.deltaY_usteps = self.multiPointController.deltaY_usteps
        self.deltaZ = self.multiPointController.deltaZ
        self.deltaZ_usteps = self.multiPointController.deltaZ_usteps
        self.dt = self.multiPointController.deltat
        self.do_autofocus = self.multiPointController.do_autofocus
        self.do_reflection_af= self.multiPointController.do_reflection_af
        self.crop_width = self.multiPointController.crop_width
        self.crop_height = self.multiPointController.crop_height
        self.counter = self.multiPointController.counter
        self.selected_configurations = self.multiPointController.selected_configurations
        self.grid_mask=self.multiPointController.grid_mask
        self.output_path:str=self.multiPointController.output_path
        self.plate_type=self.multiPointController.plate_type
        self.image_saver=self.multiPointController.image_saver
        self.image_return=image_return

        if not self.grid_mask is None:
            assert len(self.grid_mask)==self.NY
            assert len(self.grid_mask[0])==self.NX

        self.reflection_af_initialized = self.multiPointController.laserAutofocusController.is_initialized and not self.multiPointController.laserAutofocusController.x_reference is None

        self.timestamp_acquisition_started = self.multiPointController.timestamp_acquisition_started
        self.time_point:int = 0

        self.scan_coordinates_name,self.scan_coordinates_mm = scan_coordinates

        self.progress=AcqusitionProgress(
            total_steps=total_num_acquisitions,
            completed_steps=0,
            start_time=0.0,
            last_imaged_coordinates=(float("nan"),float("nan")),
        )

    def run(self):
        self.progress.start_time=time.time()
        MAIN_LOG.log("acquisition started")
        try:
            while self.time_point < self.Nt:
                MAIN_LOG.log(f"time-point {self.time_point}: starting")
                self.run_single_time_point()
                MAIN_LOG.log(f"time-point {self.time_point}: done")

                if self.multiPointController.abort_acqusition_requested:
                    raise AbortAcquisitionException()

                self.time_point = self.time_point + 1

                # continous acquisition
                if self.dt != 0.0:
                    if self.Nt==1:
                        self.time_point -= 1
                        break

                    if self.time_point == self.Nt:
                        break # no waiting after taking the last time point

                    # wait until it's time to do the next acquisition
                    next_timepoint_start_time=self.timestamp_acquisition_started + self.time_point*self.dt
                    remaining_time_s=next_timepoint_start_time-time.time()
                    MAIN_LOG.log(f"waiting for next time point in {remaining_time_s:.3f}s")

                    wait_time_step_length=1/30
                    while (remaining_time_s := next_timepoint_start_time-time.time())>0:
                        if self.multiPointController.abort_acqusition_requested:
                            MAIN_LOG.log("cancelled acquisition during waiting for next time point")
                            raise AbortAcquisitionException()
                        time.sleep(wait_time_step_length)
                        QApplication.processEvents()

            self.progress.last_completed_action="finished acquisition"
            self.signal_new_acquisition.emit(self.progress)
                        
        except AbortAcquisitionException:
            MAIN_LOG.log("acquisition successfully cancelled")

            self.progress.last_completed_action="acquisition_cancelled"
            self.signal_new_acquisition.emit(self.progress)
            
        self.finished.emit()

        MAIN_LOG.log("\nfinished multipoint acquisition\n")

    def perform_software_autofocus(self):
        """ run software autofocus to focus on current fov """

        configuration_name_AF = MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL
        config_AF = self.configuration_manager.config_by_name(configuration_name_AF)
        self.autofocusController.autofocus()
        self.autofocusController.wait_till_autofocus_has_completed()

    def image_config(self,
        config:Configuration,
        saving_path:str,
        profiler:Optional[Profiler]=None,
        counter_backlash:bool=True,
        # the params below are just for gui display purposes
        x:Optional[int]=None,y:Optional[int]=None,z:Optional[int]=None,well_name:Optional[str]=None,
    ):
        """ take image for specified configuration and save to specified path """
        
        MAIN_LOG.log(f"imaging channel {config.name}: started")

        if 'USB Spectrometer' in config.name:
            raise Exception("usb spectrometer not supported")

        with Profiler("move to channel offset",parent=profiler) as move_to_offset:
            # move to channel specific offset (if required)
            target_um=config.channel_z_offset or 0.0
            um_to_move=target_um-self.movement_deviation_from_focusplane
            if numpy.abs(um_to_move)>MACHINE_CONFIG.LASER_AUTOFOCUS_TARGET_MOVE_THRESHOLD_UM:
                self.movement_deviation_from_focusplane=target_um
                if counter_backlash:
                    self.navigation.move_z(um_to_move/1000-self.microcontroller.clear_z_backlash_mm,wait_for_completion={})
                    self.navigation.move_z(self.microcontroller.clear_z_backlash_mm,wait_for_completion={})#,wait_for_stabilization=True)
                else:
                    self.navigation.move_z(um_to_move/1000,wait_for_completion={})#,wait_for_stabilization=True)
                
                MAIN_LOG.log(f"moved to channel offset {um_to_move}um (relative to previous)")

        with Profiler("snap",parent=profiler) as snap:
            image = self.liveController.snap(config,crop=True,override_crop_height=self.crop_height,override_crop_width=self.crop_width,profiler=snap)

        with Profiler("display images",parent=profiler) as displayimage:
            # process the image -  @@@ to move to camera
            self.image_to_display.emit(image)
            self.image_to_display_multi.emit(image,config.illumination_source)

        with Profiler("enqueue image saving",parent=profiler) as enqueuesaveimages:
            if self.camera.is_color:
                with Profiler("convert color image",parent=enqueuesaveimages) as convertcolorimage:
                    if 'BF LED matrix' in config.name:
                        if MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_BF_SAVING_OPTION == BrightfieldSavingMode.RAW and image.dtype!=numpy.uint16:
                            image = cv2.cvtColor(image,cv2.COLOR_RGB2BGR)
                        elif MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_BF_SAVING_OPTION == BrightfieldSavingMode.RGB2GRAY:
                            image = cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
                        elif MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_BF_SAVING_OPTION == BrightfieldSavingMode.GREEN_ONLY:
                            image = image[:,:,1]
                    else:
                        image = cv2.cvtColor(image,cv2.COLOR_RGB2BGR)
                        
                    image=numpy.asarray(image)

            with Profiler("actual enqueue",parent=enqueuesaveimages) as actualenqueueprof:
                self.image_saver.enqueue(path=saving_path,image=image,file_format=Acquisition.IMAGE_FORMAT)

        if not self.image_return is None:
            with Profiler("broadcast image",parent=profiler):
                self.image_return(AcquisitionImageData(
                    image=image,
                    path=saving_path,
                    config=config,
                    x=x,
                    y=y,
                    z=z,
                    well_name=well_name
                ))

        self.progress.completed_steps+=1
        self.progress.last_completed_action=f"imaged config {config.name}"
        self.signal_new_acquisition.emit(self.progress)

        MAIN_LOG.log(f"imaging channel {config.name}: done")

    def image_zstack_here(self,x:int,y:int,coordinate_name:str,profiler:Optional[Profiler]=None,well_name:Optional[str]=None):
        """ x and y are for internal naming stuff only, not for anything position dependent """

        MAIN_LOG.log(f"acquiring position {coordinate_name}: started")

        ret_coords=[]

        with Profiler("run autofocus",parent=profiler) as autofocusprof:
            # autofocus
            if self.do_reflection_af == False:
                # perform AF only when (not taking z stack) or (doing z stack from center)
                if ( (self.NZ == 1) or MACHINE_CONFIG.Z_STACKING_CONFIG == 'FROM CENTER' ) and (self.do_autofocus) and (self.FOV_counter % Acquisition.NUMBER_OF_FOVS_PER_AF == 0):
                    self.perform_software_autofocus()
            else:
                # first FOV
                if self.reflection_af_initialized==False:
                    MAIN_LOG.log("setting up laser AF")
                    # initialize the reflection AF
                    self.laserAutofocusController.initialize_auto()
                    # do contrast AF for the first FOV
                    if ( (self.NZ == 1) or MACHINE_CONFIG.Z_STACKING_CONFIG == 'FROM CENTER' ) and (self.do_autofocus) and (self.FOV_counter==0):
                        self.perform_software_autofocus()
                    # set the current plane as reference
                    self.laserAutofocusController.set_reference(z_pos_mm=0.0) # z pos does not matter here
                    self.reflection_af_initialized = True
                else:
                    MAIN_LOG.log("laser AF: started")
                    self.laserAutofocusController.move_to_target(0.0)
                    MAIN_LOG.log("laser AF: done")

        if (self.NZ > 1):
            with Profiler("actual zstack (should be 0)",parent=profiler) as zstack:
                # move to bottom of the z stack
                if MACHINE_CONFIG.Z_STACKING_CONFIG == 'FROM CENTER':
                    base_z=int(-self.deltaZ_usteps*round((self.NZ-1)/2))
                    self.navigation.move_z_usteps(base_z,wait_for_completion={})
                # maneuver for achieving uniform step size and repeatability when using open-loop control
                self.navigation.move_z(-self.microcontroller.clear_z_backlash_mm,wait_for_completion={})
                self.navigation.move_z(self.microcontroller.clear_z_backlash_mm,wait_for_completion={},wait_for_stabilization=True)

                MAIN_LOG.log("moved to target z in z-stack (part 1)")

        # z-stack
        for k in range(self.NZ):
            if self.num_positions_per_well>1:
                _=next(self.well_tqdm_iter,0)

            if self.NZ > 1:
                file_ID = f'{coordinate_name}_z{k}'
            else:
                file_ID = f'{coordinate_name}'

            self.movement_deviation_from_focusplane=0.0

            with Profiler("image all configs",parent=profiler) as image_all_configs:

                # iterate through selected modes
                for config_i,config in tqdm(enumerate(self.selected_configurations),desc="channel",unit="channel",leave=False):
                    saving_path = os.path.join(self.current_path, file_ID + '_' + str(config.name).replace(' ','_'))

                    if self.multiPointController.abort_acqusition_requested:
                        raise AbortAcquisitionException()
                        
                    counter_backlash=True
                    if config_i>0:
                        previous_channel_z_offset=self.selected_configurations[config_i-1].channel_z_offset
                        current_channel_offset=self.selected_configurations[config_i-1].channel_z_offset
                        counter_backlash=previous_channel_z_offset<current_channel_offset

                    self.image_config(config=config,saving_path=saving_path,profiler=image_all_configs,counter_backlash=counter_backlash,x=x,y=y,z=k,well_name=well_name)

            with Profiler("ret coords append",parent=profiler) as retcoordsappend:
                # add the coordinate of the current location
                ret_coords.append({
                    'i':y,'j':x,'k':k,
                    'x (mm)':self.navigation.x_pos_mm,
                    'y (mm)':self.navigation.y_pos_mm,
                    'z (um)':self.navigation.z_pos_mm*1000
                })

            # register the current fov in the navigationViewer 
            self.signal_register_current_fov.emit(self.navigation.x_pos_mm,self.navigation.y_pos_mm)

            # check if the acquisition should be aborted
            if self.multiPointController.abort_acqusition_requested:
                raise AbortAcquisitionException()

            if self.NZ > 1:
                # move z
                if k < self.NZ - 1:
                    self.navigation.move_z_usteps(self.deltaZ_usteps,wait_for_completion={},wait_for_stabilization=True)
                    self.on_abort_dz_usteps = self.on_abort_dz_usteps + self.deltaZ_usteps

                MAIN_LOG.log("moved to target z in z-stack (part 3)")

            self.progress.last_completed_action="image z slice"
            self.signal_new_acquisition.emit(self.progress)
        
        if self.NZ > 1:
            # move z back
            latest_offset=-self.deltaZ_usteps*(self.NZ-1)
            if MACHINE_CONFIG.Z_STACKING_CONFIG == 'FROM CENTER':
                latest_offset+=self.deltaZ_usteps*round((self.NZ-1)/2)

            self.on_abort_dz_usteps += latest_offset
            self.navigation.move_z_usteps(latest_offset,wait_for_completion={})

            MAIN_LOG.log("moved to target z in z-stack (part 2)")

        # update FOV counter
        self.FOV_counter = self.FOV_counter + 1

        MAIN_LOG.log(f"acquiring position {coordinate_name}: done")

        return ret_coords

    @TypecheckFunction
    def image_grid_here(self,coordinates_pd:pd.DataFrame,well_name:str,profiler:Optional[Profiler]=None)->pd.DataFrame:
        """ image xyz grid starting at current position """

        if self.num_positions_per_well>1:
            # show progress when iterating over all well positions (do not differentiatte between xyz in this progress bar, it's too quick for that)
            well_tqdm=tqdm(range(self.num_positions_per_well),desc="pos in well", unit="pos",leave=False)
            self.well_tqdm_iter=iter(well_tqdm)

        leftover_x_mm=0.0
        leftover_y_mm=0.0

        # along y
        for i in range(self.NY):

            self.FOV_counter = 0 # so that AF at the beginning of each new row

            # along x
            for j in range(self.NX):

                j_actual = j if self.x_scan_direction==1 else self.NX-1-j
                site_index = 1 + j_actual + i * self.NX
                coordinate_name = f'{well_name}_s{site_index}_x{j_actual}_y{i}' # _z{k} added later (if needed)

                do_image_this_position=True

                if not self.grid_mask is None:
                    do_image_this_position=self.grid_mask[i][j_actual]

                if do_image_this_position:
                    with Profiler("move to target location",parent=profiler) as movetotargetposition:
                        self.navigation.move_by_mm(
                            x_mm=leftover_x_mm if numpy.abs(leftover_x_mm)>1e-5 else None, # only move if moving distance is larger than zero (larger than <zero plus a small value to account for floating-point errors>)
                            y_mm=leftover_y_mm if numpy.abs(leftover_y_mm)>1e-5 else None, # only move if moving distance is larger than zero (larger than <zero plus a small value to account for floating-point errors>)
                            wait_for_completion={}
                        )#,wait_for_stabilization=True)
                        leftover_y_mm=0.0
                        leftover_x_mm=0.0

                    try:
                        with Profiler("image z stack",parent=profiler) as imagezstack:
                            # update coordinates before imaging starts, because signal will be emitted for every image recorded, i.e. images would be recorded then signal with outdated position emitted
                            self.progress.last_imaged_coordinates=(self.navigation.x_pos_mm,self.navigation.y_pos_mm)
                            imaged_coords_dict_list=self.image_zstack_here(
                                x=j,y=i,
                                coordinate_name=coordinate_name,
                                profiler=imagezstack,
                                well_name=well_name,
                            )

                        with Profiler("concat pd",parent=profiler) as concat_pd:
                            coordinates_pd = pd.concat([
                                coordinates_pd,
                                pd.DataFrame(imaged_coords_dict_list)
                            ])

                    except AbortAcquisitionException:
                        if ENABLE_TQDM_STUFF:
                            self.well_tqdm_iter.close()

                        self.liveController.turn_off_illumination()

                        coordinates_pd.to_csv(os.path.join(self.current_path,'coordinates.csv'),index=False,header=True)
                        self.navigation.enable_joystick_button_action = True

                        raise AbortAcquisitionException()

                self.progress.last_completed_action="image x step in well"
                self.signal_new_acquisition.emit(self.progress)

                if self.NX > 1:
                    # move x
                    if j < self.NX - 1:
                        leftover_x_mm+=self.x_scan_direction*self.deltaX

            # move along rows in alternating directions (instead of always starting on left side of row)
            self.x_scan_direction = -self.x_scan_direction

            if self.NY > 1:
                # move y
                if i < self.NY - 1:
                    leftover_y_mm+=self.deltaY

            self.progress.last_completed_action="image y step in well"
            self.signal_new_acquisition.emit(self.progress)

        # exhaust tqdm iterator
        if self.num_positions_per_well>1:
            _=next(self.well_tqdm_iter,0)

        return coordinates_pd

    def run_single_time_point(self):
        with Profiler("run_single_time_point",parent=None,discard_if_parent_none=False) as profiler:
            if self.reflection_af_initialized:
                MAIN_LOG.log(f"moving to z reference at {self.laserAutofocusController.reference_z_height_mm:.3f}mm")
                self.laserAutofocusController.navigation.move_z_to(z_mm=self.laserAutofocusController.reference_z_height_mm,wait_for_completion={})
                MAIN_LOG.log(f"moving to z reference done")

            with self.camera.wrapper.ensure_streaming(), self.autofocusController.camera.wrapper.ensure_streaming():
                # disable joystick button action
                self.navigation.enable_joystick_button_action = False

                self.FOV_counter = 0

                MAIN_LOG.log(f"multipoint acquisition - time point {self.time_point} at {create_current_timestamp()}")

                if self.Nt > 1:
                    # for each time point, create a new folder
                    time_point_str=f"t{self.time_point:02}"
                    current_path = str(Path(self.output_path)/time_point_str)
                    self.current_path=current_path
                    os.mkdir(current_path)
                else:
                    # only one time point, save it directly in the experiment folder
                    self.current_path=str(self.output_path)

                # create a dataframe to save coordinates
                coordinates_pd = pd.DataFrame(columns = ['i', 'j', 'k', 'x (mm)', 'y (mm)', 'z (um)'])

                if not self.grid_mask is None:
                    self.num_positions_per_well=numpy.sum(self.grid_mask)*self.NZ
                else:
                    self.num_positions_per_well=self.NX*self.NY*self.NZ

                z_usteps_before_current_position_acquisition=self.navigation.z_pos_usteps

                # each region is a well
                n_regions = len(self.scan_coordinates_name)
                for coordinate_id in range(n_regions) if n_regions==1 else tqdm(range(n_regions),desc="well on plate",unit="well"):
                    coordinate_mm = self.scan_coordinates_mm[coordinate_id]
                    well_name = self.scan_coordinates_name[coordinate_id]

                    base_x=coordinate_mm[0]-self.deltaX*(self.NX-1)/2
                    base_y=coordinate_mm[1]-self.deltaY*(self.NY-1)/2

                    with Profiler("move_to_well",parent=profiler) as move_to_well_profiler:
                        # this function handles avoiding invalid physical positions etc.
                        self.navigation.move_to_mm(x_mm=base_x,y_mm=base_y,wait_for_completion={})

                    self.x_scan_direction = 1 # will be flipped between {-1, 1} to alternate movement direction in rows within the same well (instead of moving to same edge of row and wasting time by doing so)
                    self.on_abort_dx_usteps = 0
                    self.on_abort_dy_usteps = 0
                    self.on_abort_dz_usteps = 0

                    # z stacking config
                    if MACHINE_CONFIG.Z_STACKING_CONFIG == 'FROM TOP':
                        self.deltaZ_usteps = -abs(self.deltaZ_usteps)

                    with Profiler("image_grid_here",parent=profiler) as image_grid_here_profiler:
                        coordinates_pd=self.image_grid_here(coordinates_pd=coordinates_pd,well_name=well_name,profiler=image_grid_here_profiler)

                    if n_regions == 1:
                        # only move to the start position if there's only one region in the scan
                        if self.NY > 1:
                            # move y back
                            self.navigation.move_y_usteps(-self.deltaY_usteps*(self.NY-1),wait_for_completion={},wait_for_stabilization=True)
                            self.on_abort_dy_usteps = self.on_abort_dy_usteps - self.deltaY_usteps*(self.NY-1)

                        # move x back at the end of the scan
                        if self.x_scan_direction == -1:
                            self.navigation.move_x_usteps(-self.deltaX_usteps*(self.NX-1),wait_for_completion={},wait_for_stabilization=True)

                        # move z back
                        self.navigation.microcontroller.move_z_to_usteps(z_usteps_before_current_position_acquisition)
                        self.navigation.microcontroller.wait_till_operation_is_completed()

                coordinates_pd.to_csv(os.path.join(self.current_path,'coordinates.csv'),index=False,header=True)
                self.navigation.enable_joystick_button_action = True

class MultiPointController(QObject):

    acquisitionStarted = Signal()
    acquisitionFinished = Signal()
    image_to_display = Signal(numpy.ndarray)
    image_to_display_multi = Signal(numpy.ndarray,int)
    spectrum_to_display = Signal(numpy.ndarray)
    signal_register_current_fov = Signal(float,float)

    #@TypecheckFunction
    def __init__(self,
        camera:camera.Camera,
        navigationController:NavigationController,
        liveController:LiveController,
        autofocusController:AutoFocusController,
        laserAutofocusController,#:LaserAutofocusController,
        configuration_manager:ConfigurationManager,
        image_saver:ImageSaver,
        parent:Optional[Any]=None,
    ):
        QObject.__init__(self)

        self.camera = camera
        self.microcontroller = navigationController.microcontroller # to move to gui for transparency
        self.navigation = navigationController
        self.liveController = liveController
        self.autofocusController = autofocusController
        self.laserAutofocusController = laserAutofocusController
        self.configuration_manager = configuration_manager
        self.image_saver=image_saver

        self.NX:int = DefaultMultiPointGrid.DEFAULT_Nx
        self.NY:int = DefaultMultiPointGrid.DEFAULT_Ny
        self.NZ:int = DefaultMultiPointGrid.DEFAULT_Nz
        self.Nt:int = DefaultMultiPointGrid.DEFAULT_Nt
        self.deltaX:float = DefaultMultiPointGrid.DEFAULT_DX_MM
        self.deltaY:float = DefaultMultiPointGrid.DEFAULT_DY_MM
        self.deltaZ:float = DefaultMultiPointGrid.DEFAULT_DZ_MM
        self.deltat:float = DefaultMultiPointGrid.DEFAULT_DT_S

        self.do_autofocus:bool = False
        self.do_reflection_af:bool = False

        self.crop_width = Acquisition.CROP_WIDTH
        self.crop_height = Acquisition.CROP_HEIGHT
        
        self.counter:int = 0
        self.output_path: Optional[str] = None
        self.selected_configurations = []
        self.thread:Optional[QThread]=None
        self.parent = parent

        self.plate_type:Optional[str]=None

        # set some default values to avoid introducing new attributes outside constructor
        self.abort_acqusition_requested = False
        self.configuration_before_running_multipoint:Optional[Configuration] = None
        self.liveController_was_live_before_multipoint = False
        self.camera_callback_was_enabled_before_multipoint = False

    @property
    def autofocus_channel_name(self)->str:
        return MACHINE_CONFIG.MUTABLE_STATE.MULTIPOINT_AUTOFOCUS_CHANNEL

    @property
    def deltaX_usteps(self)->int:
        return self.microcontroller.mm_to_ustep_x(self.deltaX)
    @property
    def deltaY_usteps(self)->int:
        return self.microcontroller.mm_to_ustep_y(self.deltaY)
    @property
    def deltaZ_usteps(self)->int:
        return self.microcontroller.mm_to_ustep_z(self.deltaZ)

    @TypecheckFunction
    def set_NX(self,N:int):
        self.NX = N
    @TypecheckFunction
    def set_NY(self,N:int):
        self.NY = N
    @TypecheckFunction
    def set_NZ(self,N:int):
        self.NZ = N
    @TypecheckFunction
    def set_Nt(self,N:int):
        self.Nt = N

    @TypecheckFunction
    def set_deltaX(self,delta_mm:float):
        self.deltaX = delta_mm
    @TypecheckFunction
    def set_deltaY(self,delta_mm:float):
        self.deltaY = delta_mm
    @TypecheckFunction
    def set_deltaZ(self,delta_mm:float):
        self.deltaZ = delta_mm
    @TypecheckFunction
    def set_deltat(self,delta_s:float):
        self.deltat = delta_s

    @TypecheckFunction
    def set_software_af_flag(self,flag:Union[int,bool]):
        if type(flag)==bool:
            self.do_autofocus=flag
        else:
            self.do_autofocus = bool(flag)
    @TypecheckFunction
    def set_laser_af_flag(self,flag:Union[int,bool]):
        if type(flag)==bool:
            self.do_reflection_af=flag
        else:
            self.do_reflection_af = bool(flag)

    @TypecheckFunction
    def set_crop(self,crop_width:int,crop_height:int):
        self.crop_width = crop_width
        self.crop_height = crop_height

    @TypecheckFunction
    def set_selected_configurations(self, selected_configurations_name:List[str]):
        self.selected_configurations = []
        for configuration_name in selected_configurations_name:
            self.selected_configurations.append(self.configuration_manager.config_by_name(configuration_name))
        
    @TypecheckFunction
    def run_experiment(self,
        well_selection:Tuple[List[str],List[Tuple[float,float]]],
        on_new_acquisition:Optional[Callable[[AcqusitionProgress],None]],
        plate_type:str,

        grid_mask:Optional[Any]=None,
        image_return:Optional[Any]=None,
    )->Optional[QThread]:
        while not self.thread is None:
            time.sleep(0.05)
            self.thread.quit() # this should result in the self.thread.finished signal being sent, which calls self.on_thread_finished, which sets self.thread=None

        image_positions=well_selection

        num_wells=len(image_positions[0])
        if grid_mask is None:
            num_images_per_well=self.NX*self.NY*self.NZ*self.Nt
        else:
            num_images_per_well=numpy.sum(grid_mask)*self.NZ*self.Nt
        num_channels=len(self.selected_configurations)

        self.abort_acqusition_requested = False
        self.liveController_was_live_before_multipoint = False
        self.camera_callback_was_enabled_before_multipoint = False
        self.configuration_before_running_multipoint = self.liveController.currentConfiguration
        self.grid_mask=grid_mask
        self.plate_type=plate_type

        if num_wells==0:
            warning_text="No wells have been selected, so nothing to acquire. Consider selecting some wells before starting the multi point acquisition."
            raise ValueError(warning_text)
        elif num_channels==0:
            warning_text="No channels have been selected, so nothing to acquire. Consider selecting some channels before starting the multi point acquisition."
            raise ValueError(warning_text)
        elif num_images_per_well==0:
            warning_text="Somehow no images would be acquired if acquisition were to start. Maybe all positions were de-selected in the grid mask?"
            raise ValueError(warning_text)
        else:
            total_num_acquisitions=int(num_wells*num_images_per_well*num_channels)
            msg=f"starting multipoint with {num_wells} wells, {num_images_per_well} images per well, {num_channels} channels, total={total_num_acquisitions} images (AF is {'on' if self.do_autofocus or self.do_reflection_af else 'off'})"
            MAIN_LOG.log(msg)

            storage_on_device=get_storage_size_in_directory(self.output_path)
            free_space_gb=storage_on_device.free_space_bytes/1024**3
            total_space_gb=storage_on_device.total_space_bytes/1024**3

            total_imaging_size_gb=total_num_acquisitions*self.camera.ROI_width*self.camera.ROI_height*self.camera.pixel_size_byte/1024**3
            msg=f"acquisition will use {total_imaging_size_gb:.3f}GB storage (on device, {free_space_gb:.3f}/{total_space_gb:.3f}GB are availble)"
            MAIN_LOG.log(msg)
            # check if enough free space is available, and add 1GB extra on top to ensure the system can still operate smoothly once imaging is done. (assuming 1GB is enough to run the OS. might not be enough to run any program, but should be enough to not crash the computer)
            if total_imaging_size_gb>(free_space_gb+1.0):
                raise RuntimeError(f"error - imaging will use up more storage than is available on the output device! {msg}")

            self.acquisitionStarted.emit()

            # run the acquisition
            self.timestamp_acquisition_started = time.time()

            RUN_WORKER_ASYNC=False
            self.multiPointWorker = MultiPointWorker(self,image_positions,is_async=RUN_WORKER_ASYNC,total_num_acquisitions=total_num_acquisitions,image_return=image_return)
            
            if RUN_WORKER_ASYNC:
                self.thread = QThread()
                self.multiPointWorker.moveToThread(self.thread)

                # connect signals and slots
                self.thread.started.connect(self.multiPointWorker.run)
                if not on_new_acquisition is None:
                    self.multiPointWorker.signal_new_acquisition.connect(on_new_acquisition)

                self.multiPointWorker.image_to_display.connect(self.image_to_display.emit)
                self.multiPointWorker.image_to_display_multi.connect(self.image_to_display_multi.emit)
                self.multiPointWorker.spectrum_to_display.connect(self.slot_spectrum_to_display)
                self.multiPointWorker.signal_register_current_fov.connect(self.slot_register_current_fov)

                self.multiPointWorker.finished.connect(self.on_multipointworker_finished)

                self.thread.finished.connect(self.on_thread_finished)
                
                self.thread.start()

                return self.thread
            else:
                if not on_new_acquisition is None:
                    self.multiPointWorker.signal_new_acquisition.connect(on_new_acquisition)

                # self.multiPointWorker.image_to_display.connect(self.image_to_display.emit) # adds an hour or two to the imaging time.. ?!
                self.multiPointWorker.image_to_display_multi.connect(self.image_to_display_multi.emit)
                self.multiPointWorker.spectrum_to_display.connect(self.slot_spectrum_to_display)
                self.multiPointWorker.signal_register_current_fov.connect(self.slot_register_current_fov)

                self.multiPointWorker.finished.connect(self._on_acquisition_completed)
                    
                self.multiPointWorker.run()

    def on_multipointworker_finished(self):
        self._on_acquisition_completed()
        self.multiPointWorker.deleteLater()
        self.thread.quit()

    def on_thread_finished(self):
        self.thread.quit()
        self.multiPointWorker=None
        self.thread=None

    def _on_acquisition_completed(self):        
        # emit the acquisition finished signal to enable the UI
        self.acquisitionFinished.emit()

    def request_abort_aquisition(self):
        self.abort_acqusition_requested = True

    def _slot_image_to_display(self,image):
        self.image_to_display.emit(image)

    def slot_spectrum_to_display(self,data):
        self.spectrum_to_display.emit(data)

    def _slot_image_to_display_multi(self,image,illumination_source):
        self.image_to_display_multi.emit(image,illumination_source)

    def slot_register_current_fov(self,x_mm,y_mm):
        self.signal_register_current_fov.emit(x_mm,y_mm)

