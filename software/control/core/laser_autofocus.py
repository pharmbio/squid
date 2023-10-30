import os 
os.environ["QT_API"] = "pyqt5"

# qt libraries
from qtpy.QtCore import QObject, Signal, QMutex, QEventLoop
from qtpy.QtWidgets import QApplication

from control._def import MACHINE_CONFIG, MAIN_LOG
from control.typechecker import TypecheckFunction
from typing import Optional

import time, math
import numpy as np
import scipy
import scipy.signal

import control.microcontroller as microcontroller
import control.camera as camera
from control.core import LiveController,NavigationController

import matplotlib.pyplot as plt

class LaserAutofocusController(QObject):

    image_to_display = Signal(np.ndarray)
    signal_displacement_um = Signal(float)

    def __init__(self,
        microcontroller:microcontroller.Microcontroller,
        camera:camera.Camera, # focus camera
        liveController:LiveController,
        navigationController:NavigationController,
        has_two_interfaces:bool=True,
        use_glass_top:bool=True
    ):
        QObject.__init__(self)
        self.microcontroller = microcontroller
        self.camera = camera
        self.liveController = liveController
        self.navigation = navigationController

        self.is_initialized:bool = False
        self.x_reference:Optional[float] = None
        self.um_per_px:float = 1.0
        self.x_offset:int = 0
        self.y_offset:int = 0
        self.width:int = 3088
        self.height:int = 2064
        self.reference_z_height_mm:float=0.0

        self.has_two_interfaces:bool = has_two_interfaces # e.g. air-glass and glass water, set to false when (1) using oil immersion (2) using 1 mm thick slide (3) using metal coated slide or Si wafer
        self.use_glass_top:bool = use_glass_top
        self.spot_spacing_pixels = None # spacing between the spots from the two interfaces (unit: pixel)

        self.reset_camera_sensor_crop() # camera crop is preserved between program restarts. mainly for debugging purposes, reset camera sensor crop so that full sensor is used on program startup

    def initialize_manual(self, x_offset:int, y_offset:int, width:int, height:int, um_per_px:float, x_reference:float):
        # x_reference is relative to the full sensor
        self.um_per_px = um_per_px
        self.x_offset = int((x_offset//8)*8)
        self.y_offset = int((y_offset//2)*2)
        self.width = int((width//8)*8)
        self.height = int((height//2)*2)

        self.camera.set_ROI(self.x_offset,self.y_offset,self.width,self.height)

        self.x_reference = x_reference - self.x_offset # self.x_reference is relative to the cropped region
        self.is_initialized = True

    def reset_camera_sensor_crop(self):
        self.camera.set_ROI(0,0,None,None) # set offset first
        self.camera.set_ROI(0,0,3088,2064)

    def initialize_auto(self):

        # set camera to use full sensor
        self.reset_camera_sensor_crop()

        # update camera settings
        self.camera.set_exposure_time(MACHINE_CONFIG.FOCUS_CAMERA_EXPOSURE_TIME_MS)
        self.camera.set_analog_gain(MACHINE_CONFIG.FOCUS_CAMERA_ANALOG_GAIN)

        with self.camera.wrapper.ensure_streaming():
            # get laser spot location
            x,y = self._get_laser_spot_centroid()

            x_offset = 0 # x - MACHINE_CONFIG.LASER_AF_CROP_WIDTH/2
            y_offset = y - MACHINE_CONFIG.LASER_AF_CROP_HEIGHT/2
            #print('laser spot location on the full sensor is (' + str(int(x)) + ',' + str(int(y)) + ')')

            # set camera crop
            self.initialize_manual(x_offset, y_offset, MACHINE_CONFIG.LASER_AF_CROP_WIDTH, MACHINE_CONFIG.LASER_AF_CROP_HEIGHT, 1.0, x)

            # move z
            z_mm_movement_range=0.1
            z_mm_backlash_counter=self.microcontroller.clear_z_backlash_mm
            self.navigation.move_z(z_mm=-(z_mm_movement_range/2+z_mm_backlash_counter),wait_for_completion={},wait_for_stabilization=True)
            self.navigation.move_z(z_mm=z_mm_backlash_counter,wait_for_completion={},wait_for_stabilization=True)

            x0,y0 = self._get_laser_spot_centroid()

            self.navigation.move_z(z_mm=z_mm_movement_range/2,wait_for_completion={},wait_for_stabilization=True)

            x1,y1 = self._get_laser_spot_centroid()

            self.navigation.move_z(z_mm=z_mm_movement_range/2,wait_for_completion={},wait_for_stabilization=True)

            x2,y2 = self._get_laser_spot_centroid()

            self.navigation.move_z(z_mm=-(z_mm_movement_range/2),wait_for_completion={},wait_for_stabilization=True)

            # calculate the conversion factor
            self.um_per_px = z_mm_movement_range*1000/(x2-x0)

            # set reference
            self.x_reference = x1

        MAIN_LOG.log("laser AF initialization done")

    def measure_displacement(self,override_num_images:Optional[int]=None)->float:
        assert self.is_initialized and not self.x_reference is None

        # get laser spot location
        # sometimes one of the two expected dots cannot be found in _get_laser_spot_centroid because the plate is so far off the focus plane though, catch that case
        try:
            x,y = self._get_laser_spot_centroid(num_images=override_num_images or MACHINE_CONFIG.LASER_AF_AVERAGING_N_FAST)

            # calculate displacement
            displacement_um = (x - self.x_reference)*self.um_per_px
        except:
            displacement_um=float('nan')

        self.signal_displacement_um.emit(displacement_um)

        if math.isnan(displacement_um):
            MAIN_LOG.log("! error - displacement was measured as NaN. Either you are out of range for the laser AF (more than 200um away from focus plane), or something has gone wrong. Make sure that the laser AF laser is not currently used for live imaging. Displacement measured as NaN is treated as zero in the program, to avoid crashing.")

        return displacement_um

    def move_to_target(self,target_um:float,max_repeats:int=MACHINE_CONFIG.LASER_AUTOFOCUS_MOVEMENT_MAX_REPEATS,counter_backlash:bool=True):
        with self.camera.wrapper.ensure_streaming():
            current_displacement_um = self.measure_displacement()
            if math.isnan(current_displacement_um):
                MAIN_LOG.log("laser AF: failed with NaN")
                return
            
            total_movement_um=0.0

            num_repeat=0
            while np.abs(um_to_move := target_um - current_displacement_um) >= MACHINE_CONFIG.LASER_AUTOFOCUS_TARGET_MOVE_THRESHOLD_UM:
                if math.isnan(current_displacement_um):
                    MAIN_LOG.log("laser AF: failed with NaN after {num_repeat} iterations moving {total_movement_um:.3f}um")
                    break

                # limit the range of movement
                um_to_move = np.clip(um_to_move,MACHINE_CONFIG.LASER_AUTOFOCUS_MOVEMENT_BOUNDARY_LOWER,MACHINE_CONFIG.LASER_AUTOFOCUS_MOVEMENT_BOUNDARY_UPPER)

                #print(f"laser af - rep {num_repeat}: off by {current_displacement_um:.2f} from target {target_um:.2f} therefore moving by {um_to_move:.2f}")

                if counter_backlash:
                    self.navigation.move_z(um_to_move/1000-self.microcontroller.clear_z_backlash_mm,wait_for_completion={})
                    self.navigation.move_z(self.microcontroller.clear_z_backlash_mm,wait_for_completion={})
                else:
                    self.navigation.move_z(um_to_move/1000,wait_for_completion={})

                current_displacement_um = self.measure_displacement()
                num_repeat+=1
                total_movement_um+=um_to_move

                if num_repeat==max_repeats:
                    MAIN_LOG.log(f"laser AF: failed with measured offset {current_displacement_um:.3f}um and target {target_um}um")
                    break

            MAIN_LOG.log(f"laser AF: done after {num_repeat} iterations and moving {total_movement_um:.3f}um")

    @TypecheckFunction()
    def set_reference(self,z_pos_mm:float):
        assert self.is_initialized

        # counter backlash
        self.navigation.move_z(-self.microcontroller.clear_z_backlash_mm,wait_for_completion={},wait_for_stabilization=True)
        self.navigation.move_z(self.microcontroller.clear_z_backlash_mm,wait_for_completion={},wait_for_stabilization=True)

        self.microcontroller.turn_on_AF_laser()
        self.microcontroller.wait_till_operation_is_completed(timeout_limit_s=None,time_step=0.001)

        x,y = self._get_laser_spot_centroid()

        self.microcontroller.turn_off_AF_laser()
        self.microcontroller.wait_till_operation_is_completed(timeout_limit_s=None,time_step=0.001)

        self.x_reference = x
        self.signal_displacement_um.emit(0)

        self.reference_z_height_mm=z_pos_mm

    def _get_laser_spot_centroid(self,num_images:Optional[int]=None):
        """
            get position of laser dot on camera sensor to calculated displacement from

            num_images is number of images that are taken to calculate the average dot position from (eliminates some noise). defaults to a large number for higher precision.
        """

        tmp_x = 0
        tmp_y = 0

        start_time=time.time()
        imaging_times=[]

        if num_images is None:
            num_images=MACHINE_CONFIG.LASER_AF_AVERAGING_N_PRECISE

        with self.camera.wrapper.ensure_streaming():
            for i in range(num_images):
                DEBUG_THIS_STUFF=False

                # try acquiring camera image until one arrives (can sometimes miss an image for some reason)
                image=None
                current_counter=0
                take_image_start_time=time.time()
                while image is None:
                    if DEBUG_THIS_STUFF:
                        print(f"laser autofocus centroid spot imaging attempt: {current_counter=}")
                        current_counter+=1
            
                    image = self.liveController.snap(self.liveController.currentConfiguration)

                imaging_times.append(time.time()-take_image_start_time)

                # optionally display the image
                if MACHINE_CONFIG.LASER_AF_DISPLAY_SPOT_IMAGE:
                    self.image_to_display.emit(image)

                # calculate centroid
                x,y = self._calculate_centroid(image)

                if DEBUG_THIS_STUFF and False:
                    print(f"{x = } {(MACHINE_CONFIG.LASER_AF_CROP_WIDTH/2) = }")
                    print(f"{y = } {(MACHINE_CONFIG.LASER_AF_CROP_HEIGHT/2) = }")

                    plt.imshow(image,cmap="gist_gray")
                    plt.scatter([x],[y],marker="x",c="green")
                    plt.show()

                tmp_x += x
                tmp_y += y

        if DEBUG_THIS_STUFF:
            imaging_times_str=", ".join([f"{i:.3f}" for i in imaging_times])
            print(f"calculated centroid in {(time.time()-start_time):.3f}s ({imaging_times_str})")

        x = tmp_x/num_images
        y = tmp_y/num_images


        return x,y

    def _calculate_centroid(self,image):
        if self.has_two_interfaces == False:
            h,w = image.shape
            x,y = np.meshgrid(range(w),range(h))
            I = image.astype(float)
            I = I - np.amin(I)
            I[I/np.amax(I)<0.2] = 0
            x = np.sum(x*I)/np.sum(I)
            y = np.sum(y*I)/np.sum(I)
            return x,y
        else:
            I = image
            # get the y position of the spots
            tmp = np.sum(I,axis=1)
            y0 = np.argmax(tmp)
            # crop along the y axis
            I = I[y0-96:y0+96,:]
            # signal along x
            tmp = np.sum(I,axis=0)
            # find peaks
            peak_locations,_ = scipy.signal.find_peaks(tmp,distance=100)
            idx = np.argsort(tmp[peak_locations])
            if len(idx)>0:
                peak_0_location = peak_locations[idx[-1]]
            if len(idx)>1:
                peak_1_location = peak_locations[idx[-2]] # for air-glass-water, the smaller peak corresponds to the glass-water interface
            if len(idx)==0:
                raise Exception("did not find any peaks in laser AF signal. this is a major problem.")
            
            # choose which surface to use
            if self.use_glass_top:
                assert len(idx)>1, "only found a single peak in the laser af signal, but trying to use the second one."
                x1 = peak_1_location
            else:
                x1 = peak_0_location
            # find centroid
            h,w = I.shape
            x,y = np.meshgrid(range(w),range(h))
            I = I[:,max(0,x1-64):min(w-1,x1+64)]
            x = x[:,max(0,x1-64):min(w-1,x1+64)]
            y = y[:,max(0,x1-64):min(w-1,x1+64)]
            I = I.astype(float)
            I = I - np.amin(I)
            I[I/np.amax(I)<0.1] = 0
            x1 = np.sum(x*I)/np.sum(I)
            y1 = np.sum(y*I)/np.sum(I)
            return x1,y0-96+y1

  