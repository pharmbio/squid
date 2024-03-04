import time
import numpy
import importlib

import control.gxipy as gx
from control.gxipy import gxiapi

from control._def import *
from typing import Optional, Any

from control.typechecker import TypecheckFunction

from qtpy.QtWidgets import QApplication

from functools import wraps

def get_sn_by_model(model_name:str)->Optional[Any]:
    try:
        device_manager = gx.DeviceManager()
        device_num, device_info_list = device_manager.update_device_list()
    except:
        device_num = 0

    if device_num > 0:
        for i in range(device_num):
            if device_info_list[i]['model_name'] == model_name:
                return device_info_list[i]['sn']
            
    return None # return None if no device with the specified model_name is connected

def retry_on_failure(
    timeout_s:float=0.1,
    allow_retry_check:Optional[callable]=None,
    try_recover:Optional[callable]=None,
    function_uses_self:bool=False
):
    """

    calls function with arguments. if this throws any exception:
        if do_allow_retry is provided, this function is called with the exception, and calling the original function is only retried of do_allow_retry(e) return True
        before the function should be retried after exception, try_recover is called, if present

    if function_uses_self is True:
        try_recover is called as try_recover()(args[0],/*further args*/)
        this is because retry_on_failure as decorator on instance methods cannot capture the surrounding class
        same for allow_retry_check with is then called as allow_retry_check()(args[0],/*further args*/)

    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args,**kwargs):
            # use loop to avoid potentially very deep recursion
            while True:
                try:
                    # if function succeeds, this return will 'break' the loop
                    return func(*args,**kwargs)
                except Exception as e:
                    do_allow_retry=True
                    if allow_retry_check is not None:
                        if function_uses_self:
                            do_allow_retry=allow_retry_check()(args[0],e)
                        else:
                            do_allow_retry=allow_retry_check(e)

                    if not do_allow_retry:
                        raise e

                if try_recover is not None:
                    if function_uses_self:
                        try_recover()(args[0])
                    else:
                        try_recover()
                
                time.sleep(timeout_s)

        return wrapper
    return decorator

class Camera(object):

    @TypecheckFunction
    def __init__(self,
        sn:Optional[str]=None,
        model:Optional[str]=None,
        is_global_shutter:bool=False,
        rotate_image_angle:int=0,
        flip_image:Optional[str]=None,
        used_for_laser_autofocus:bool=False
    ):

        # many to be purged
        self.sn = sn
        self.model = model
        self.is_global_shutter = is_global_shutter
        self.device_manager = gx.DeviceManager()
        self.device_info_list = None
        self.device_index = 0
        self.camera:Optional[gxiapi.Device] = None
        self.is_color = None
        self.gamma_lut = None
        self.contrast_lut = None
        self.color_correction_param = None

        self.rotate_image_angle = rotate_image_angle
        self.flip_image = flip_image

        self.exposure_time_ms = 10.0
        self.analog_gain = None
        self.frame_ID = -1
        self.frame_ID_software = -1
        self.frame_ID_offset_hardware_trigger = 0
        self.timestamp = 0

        self.image_locked = False
        self.current_frame:Optional[numpy.ndarray] = None

        self.callback_is_enabled = False
        self.is_streaming = False

        self.GAIN_MAX = 24
        self.GAIN_MIN = 0
        self.GAIN_STEP = 1
        self.EXPOSURE_TIME_MS_MIN = 0.01
        self.EXPOSURE_TIME_MS_MAX = 1000-62.5-1.5 # technically 1000, but hardware trigger adds 62.5ms overhead (then add 1.5 extra to make sure the limit is not hit!)

        self.ROI_offset_x = CAMERA.ROI_OFFSET_X_DEFAULT
        self.ROI_offset_y = CAMERA.ROI_OFFSET_Y_DEFAULT
        self.ROI_width = CAMERA.ROI_WIDTH_DEFAULT
        self.ROI_height = CAMERA.ROI_HEIGHT_DEFAULT

        self.trigger_mode = None
        self.pixel_size_byte = 1

        # below are values for IMX226 (MER2-1220-32U3M) - to make configurable 
        self.row_period_us = 10
        self.row_numbers = 3036
        self.exposure_delay_us_8bit = 650
        self.exposure_delay_us = self.exposure_delay_us_8bit*self.pixel_size_byte
        self.strobe_delay_us = self.exposure_delay_us + self.row_period_us*self.pixel_size_byte*(self.row_numbers-1)

        self.pixel_format=None

        self.is_live = False # this determines whether a new frame received will be handled in the streamHandler
        # mainly for discarding the last frame received after stop_live() is called, where illumination is being turned off during exposure

        self.used_for_laser_autofocus:bool=used_for_laser_autofocus

        self.in_a_state_to_be_used_directly=False

    def open_default(self):
        camera_identifier=None
        if self.sn is not None:
            camera_identifier=f"sn: {self.sn}"
            MAIN_LOG.log(f"connecting camera by sn {self.sn=}")
            self.camera = self.device_manager.open_device_by_sn(self.sn)
        elif self.model is not None:
            camera_identifier=f"model: {self.model}"
            MAIN_LOG.log(f"connecting camera by model {self.model=}")
            camera_sn=get_sn_by_model(self.model)
            if camera_sn is not None:
                self.camera=self.device_manager.open_device_by_sn(camera_sn)
            else:
                error_msg=f"no camera of model {self.model} found"
                MAIN_LOG.log(error_msg)
                raise RuntimeError(error_msg)
        else:
            assert not self.device_index is None
            self.camera = self.device_manager.open_device_by_index(self.device_index + 1)

        if self.camera is None:
            raise RuntimeError("found camera, but failed to connect")
        
        MAIN_LOG.log(f"camera connected: {camera_identifier}")
        
        assert not self.camera is None
        self.is_color = self.camera.PixelColorFilter.is_implemented()
        # self._update_image_improvement_params()
        # self.camera.register_capture_callback(self,self._on_frame_callback)
        if self.is_color:
            # self.set_wb_ratios(self.get_awb_ratios())
            print(self.get_awb_ratios())
            # self.set_wb_ratios(1.28125,1.0,2.9453125)
            self.set_wb_ratios(2,1,2)

        # temporary
        # self.camera.AcquisitionFrameRate.set(1000)
        # self.camera.AcquisitionFrameRateMode.set(gx.GxSwitchEntry.ON)

        # turn off device link throughput limit
        self.camera.DeviceLinkThroughputLimitMode.set(gx.GxSwitchEntry.OFF)

        # set this to continuous for -> stream on called once -> new image acquired on every trigger
        supported_acquisition_modes=[v for k,v in self.camera.AcquisitionMode.get_range().items()]
        assert gx.GxAcquisitionModeEntry.CONTINUOUS in supported_acquisition_modes, f"gx.GxAcquisitionModeEntry.CONTINUOUS not in {self.camera.AcquisitionMode.get_range()}"
        self.camera.AcquisitionMode.set(gx.GxAcquisitionModeEntry.CONTINUOUS)

        self.set_pixel_format(list(self.camera.PixelFormat.get_range().keys())[0])

        self.start_streaming() # debug , maybe temporary? there does not seem to be a reason to not just stream at all times...
        
    @TypecheckFunction
    def open(self,index:int=0):
        (device_num, self.device_info_list) = self.device_manager.update_device_list()
        if device_num == 0:
            raise RuntimeError('Could not find any USB camera devices!')
        
        if self.sn is None and self.model is None:
            self.device_index = index
            
        self.open_default()

    @TypecheckFunction
    def open_by_sn(self,sn:str):
        (device_num, self.device_info_list) = self.device_manager.update_device_list()
        if device_num == 0:
            raise RuntimeError('Could not find any USB camera devices!')

        self.camera = self.device_manager.open_device_by_sn(sn)
        assert not self.camera is None
        self.is_color = self.camera.PixelColorFilter.is_implemented()
        self._update_image_improvement_params()

    @TypecheckFunction
    def close(self):
        assert self.camera is not None
        self.camera.close_device()
        self.device_info_list = None
        self.camera = None
        self.is_color = None
        self.gamma_lut = None
        self.contrast_lut = None
        self.color_correction_param = None
        self.last_raw_image = None
        self.last_converted_image = None
        self.last_numpy_image = None

    @retry_on_failure(
        function_uses_self=True,
        try_recover=lambda:Camera.attempt_reconnection,
        allow_retry_check=lambda:Camera.exception_shows_camera_connection_issue,
    )
    @TypecheckFunction
    def set_exposure_time(self,exposure_time_ms:float):
        assert not self.camera is None
        if self.exposure_time_ms!=exposure_time_ms: # takes 10ms, so avoid if possible
            self.exposure_time_ms = exposure_time_ms
            self.update_camera_exposure_time()

    @retry_on_failure(
        function_uses_self=True,
        try_recover=lambda:Camera.attempt_reconnection,
        allow_retry_check=lambda:Camera.exception_shows_camera_connection_issue,
    )
    @TypecheckFunction
    def update_camera_exposure_time(self):
        assert not self.camera is None

        camera_exposure_time_range=self.camera.ExposureTime.get_range()
        min_exposure_time_us=camera_exposure_time_range['min']
        max_exposure_time_us=camera_exposure_time_range['max']

        camera_exposure_time_us=self.exposure_time_ms * 1000

        if (not self.is_global_shutter) and (self.trigger_mode == TriggerMode.HARDWARE):
            additional_exposure_time=self.exposure_delay_us + self.row_period_us*self.pixel_size_byte*(self.row_numbers-1) + 500 # add an additional 500 us so that the illumination can fully turn off before rows start to end exposure
            camera_exposure_time_us += additional_exposure_time

        if camera_exposure_time_us < min_exposure_time_us:
            print(f"camera exposure time is {camera_exposure_time_us}us but must be at least {min_exposure_time_us}us. exposure time will be automatically set to the closest valid value.")
            camera_exposure_time_us=min_exposure_time_us
        elif camera_exposure_time_us > max_exposure_time_us:
            print(f"camera exposure time is {camera_exposure_time_us}us but must not be above {max_exposure_time_us}us. exposure time will be automatically set to the closest valid value.")
            camera_exposure_time_us=max_exposure_time_us
        
        self.camera.ExposureTime.set(camera_exposure_time_us)

    @retry_on_failure(
        function_uses_self=True,
        try_recover=lambda:Camera.attempt_reconnection,
        allow_retry_check=lambda:Camera.exception_shows_camera_connection_issue,
    )
    @TypecheckFunction
    def set_analog_gain(self,analog_gain:float):
        assert not self.camera is None
        if self.analog_gain!=analog_gain: # takes 10ms, so avoid if possible
            self.analog_gain = analog_gain
            self.camera.Gain.set(analog_gain)

    @TypecheckFunction
    def get_awb_ratios(self):
        assert not self.camera is None
        self.camera.BalanceWhiteAuto.set(2)
        self.camera.BalanceRatioSelector.set(0)
        awb_r = self.camera.BalanceRatio.get()
        self.camera.BalanceRatioSelector.set(1)
        awb_g = self.camera.BalanceRatio.get()
        self.camera.BalanceRatioSelector.set(2)
        awb_b = self.camera.BalanceRatio.get()
        return (awb_r, awb_g, awb_b)

    @TypecheckFunction
    def set_wb_ratios(self, wb_r:Optional[float]=None, wb_g:Optional[float]=None, wb_b:Optional[float]=None):
        assert not self.camera is None
        self.camera.BalanceWhiteAuto.set(0)
        if wb_r is not None:
            self.camera.BalanceRatioSelector.set(0)
            awb_r = self.camera.BalanceRatio.set(wb_r)
        if wb_g is not None:
            self.camera.BalanceRatioSelector.set(1)
            awb_g = self.camera.BalanceRatio.set(wb_g)
        if wb_b is not None:
            self.camera.BalanceRatioSelector.set(2)
            awb_b = self.camera.BalanceRatio.set(wb_b)

    @TypecheckFunction
    def set_reverse_x(self,value:bool):
        assert not self.camera is None
        self.camera.ReverseX.set(value)

    @TypecheckFunction
    def set_reverse_y(self,value:bool):
        assert not self.camera is None
        self.camera.ReverseY.set(value)

    def exception_shows_camera_connection_issue(self,e)->bool:
        QApplication.processEvents()
        
        if self.camera is None or str(e.__class__.__module__)=="control.gxipy.gxiapi":
            e_classname=str(e.__class__.__name__)
            
            if self.camera is None or e_classname=="OffLine":
                MAIN_LOG.log("no camera connected")

            elif e_classname=="Timeout":
                MAIN_LOG.log("camera communication timeout")

            else:
                MAIN_LOG.log(f"unknown camera error {e_classname}")
                return False
            
            return True
        else:
            return False
        
    def attempt_reconnection(self):
        # try to close the device handle, and ignore failures
        try:
            self.close()
        except Exception as e:
            pass

        # attempt reconnecting, ignore failures and recurse (into sleep + retry)
        try:
            self.open_default()
        except Exception as e:
            pass

        # if software expects camera to be streaming, actually start streaming after reconnect
        if self.is_streaming:
            # reset flag to actually start streaming again
            self.is_streaming=False
            self.start_streaming()

        # after reconnection, if these values have been set before (at runtime), apply them to the camera again
        if self.exposure_time_ms:
            self.set_exposure_time(self.exposure_time_ms)
        if self.analog_gain:
            self.set_analog_gain(self.analog_gain)

    @retry_on_failure(
        function_uses_self=True,
        try_recover=lambda:Camera.attempt_reconnection,
        allow_retry_check=lambda:Camera.exception_shows_camera_connection_issue,
    )
    @TypecheckFunction
    def start_streaming(self):
        if not self.is_streaming:
            assert not self.camera is None
            
            self.camera.stream_on()

            self.is_streaming = True

    @retry_on_failure(
        function_uses_self=True,
        try_recover=lambda:Camera.attempt_reconnection,
        allow_retry_check=lambda:Camera.exception_shows_camera_connection_issue,
    )
    @TypecheckFunction
    def stop_streaming(self):
        """ this takes 350ms!!!! avoid calling this function if at all possible! """

        # under some weird circumstances (actually a race condition....) this camera object can have been destroyed before this callback is called, e.g. when the program is closed while a live view is active (this should not happen, but it does)
        if self.is_streaming and not self.camera is None:
            self.camera.stream_off()
                    
            self.is_streaming = False

    @TypecheckFunction
    def set_pixel_format(self,pixel_format:str):
        assert not self.camera is None
        if self.is_streaming == True:
            was_streaming = True
            self.stop_streaming()
        else:
            was_streaming = False

        if self.camera.PixelFormat.is_implemented() and self.camera.PixelFormat.is_writable():
            pixel_format_found=False

            for camera_pixel_format in CAMERA_PIXEL_FORMATS:
                if camera_pixel_format.value.name == pixel_format:
                    self.camera.PixelFormat.set(camera_pixel_format.value.gx_pixel_format)
                    self.pixel_size_byte = camera_pixel_format.value.num_bytes_per_pixel

                    self.pixel_format = camera_pixel_format

                    pixel_format_found=True
                    break

            if not pixel_format_found:
                assert False, f"pixel format {pixel_format} is not valid"
        else:
            raise RuntimeError("pixel format is not implemented or not writable")

        if was_streaming:
           self.start_streaming()

        # update the exposure delay and strobe delay
        self.exposure_delay_us = self.exposure_delay_us_8bit*self.pixel_size_byte
        self.strobe_delay_us = self.exposure_delay_us + self.row_period_us*self.pixel_size_byte*(self.row_numbers-1)

    @TypecheckFunction
    def set_software_triggered_acquisition(self):
        was_streaming=self.is_streaming

        if was_streaming:
            self.stop_streaming()

        assert not self.camera is None
        self.camera.TriggerMode.set(gx.GxSwitchEntry.ON)
        self.camera.TriggerSource.set(gx.GxTriggerSourceEntry.SOFTWARE)
        self.trigger_mode = TriggerMode.SOFTWARE
        self.update_camera_exposure_time()

        if was_streaming:
            self.start_streaming()

    @TypecheckFunction
    def set_hardware_triggered_acquisition(self):
        was_streaming=self.is_streaming

        if was_streaming:
            self.stop_streaming()

        assert not self.camera is None
        self.camera.TriggerMode.set(gx.GxSwitchEntry.ON)
        self.camera.TriggerSource.set(gx.GxTriggerSourceEntry.LINE2)
        # self.camera.TriggerSource.set(gx.GxTriggerActivationEntry.RISING_EDGE)
        self.frame_ID_offset_hardware_trigger = None
        self.trigger_mode = TriggerMode.HARDWARE
        self.update_camera_exposure_time()

        if was_streaming:
            self.start_streaming()

    @retry_on_failure(
        function_uses_self=True,
        try_recover=lambda:Camera.attempt_reconnection,
        allow_retry_check=lambda:Camera.exception_shows_camera_connection_issue,
    )
    @TypecheckFunction
    def send_trigger(self):
        assert not self.camera is None
        if not self.is_streaming:
            self.start_streaming()
            MAIN_LOG.log('trigger sent with delay - camera was not streaming')

        self.camera.TriggerSoftware.send_command()

    @TypecheckFunction
    def rescale_raw_image(self,raw_image:gxiapi.RawImage)->numpy.ndarray:
        if self.is_color:
            rgb_image = raw_image.convert("RGB")
            numpy_image = rgb_image.get_numpy_array()

            if self.pixel_format == CAMERA_PIXEL_FORMATS.BAYER_RG12:
                numpy_image = numpy_image << 4
        else:
            numpy_image = raw_image.get_numpy_array()

            if self.pixel_format == CAMERA_PIXEL_FORMATS.MONO10:
                numpy_image = numpy_image << 6
            elif self.pixel_format == CAMERA_PIXEL_FORMATS.MONO12:
                numpy_image = numpy_image << 4
            elif self.pixel_format == CAMERA_PIXEL_FORMATS.MONO14:
                numpy_image = numpy_image << 2

        return numpy_image

    @TypecheckFunction
    def read_frame(self,timeout_overhead_s:float=1.0)->numpy.ndarray:
        if self.camera is None:
            raise RuntimeError("camera (connection) is suddenly gone")

        start_time=time.time()
        raw_image=None
        while True:
            time.sleep(0.005) # arbitrary short sleep
            QApplication.processEvents()
            raw_image = self.camera.data_stream[self.device_index].get_image()

            image_recording_incomplete=(raw_image is None) or (raw_image.get_status()==gx.GxFrameStatusList.INCOMPLETE)
            if not image_recording_incomplete:
                break

            if (time.time()-start_time)>timeout_overhead_s:
                error_msg=f"camera frame did not arrive within time limit ({timeout_overhead_s:.3f})s"
                raise RuntimeError(error_msg)

        numpy_image = self.rescale_raw_image(raw_image)

        # self.current_frame = numpy_image
        return numpy_image

    @TypecheckFunction
    def _on_frame_callback(self, user_param:Optional[Any], raw_image:Optional[gxiapi.RawImage]):
        if raw_image is None:
            MAIN_LOG.log("Getting image failed.")
            return
            
        if raw_image.get_status() != 0:
            MAIN_LOG.log("Got an incomplete frame")
            return

        if self.image_locked:
            MAIN_LOG.log('last image is still being processed, a frame is dropped')
            return

        numpy_image = self.rescale_raw_image(raw_image)

        if numpy_image is None:
            return

        self.current_frame = numpy_image
        self.frame_ID_software = self.frame_ID_software + 1
        self.frame_ID = raw_image.get_frame_id()
        if self.trigger_mode == TriggerMode.HARDWARE:
            if self.frame_ID_offset_hardware_trigger == None:
                self.frame_ID_offset_hardware_trigger = self.frame_ID
            self.frame_ID = self.frame_ID - self.frame_ID_offset_hardware_trigger
        self.timestamp = time.time()
        self.new_image_callback_external(self)

        # self.frameID = self.frameID + 1
        # print(self.frameID)
    
    @TypecheckFunction
    def set_ROI(self,offset_x:Optional[int]=None,offset_y:Optional[int]=None,width:Optional[int]=None,height:Optional[int]=None,repeat_crop:bool=True):
        # stop streaming if streaming is on
        if self.is_streaming == True:
            was_streaming = True
            self.stop_streaming()
        else:
            was_streaming = False

        if offset_x is not None:
            self.ROI_offset_x = offset_x
            # update the camera setting
            if self.camera.OffsetX.is_implemented() and self.camera.OffsetX.is_writable():
                self.camera.OffsetX.set(self.ROI_offset_x)
            else:
                MAIN_LOG.log("OffsetX is not implemented or not writable")

        if offset_y is not None:
            self.ROI_offset_y = offset_y
            # update the camera setting
            if self.camera.OffsetY.is_implemented() and self.camera.OffsetY.is_writable():
                self.camera.OffsetY.set(self.ROI_offset_y)
            else:
                MAIN_LOG.log("OffsetX is not implemented or not writable")

        if width is not None:
            self.ROI_width = width
            # update the camera setting
            if self.camera.Width.is_implemented() and self.camera.Width.is_writable():
                self.camera.Width.set(self.ROI_width)
            else:
                MAIN_LOG.log("OffsetX is not implemented or not writable")

        if height is not None:
            self.ROI_height = height
            # update the camera setting
            if self.camera.Height.is_implemented() and self.camera.Height.is_writable():
                self.camera.Height.set(self.ROI_height)
            else:
                MAIN_LOG.log("Height is not implemented or not writable")

        # restart streaming if it was previously on
        if was_streaming == True:
            self.start_streaming()

        if repeat_crop:
            # call again to account for complex situations regarding incresase/decrease of offset/size
            self.set_ROI(offset_x,offset_y,width,height,repeat_crop=False)

    def reset_camera_acquisition_counter(self):
        assert not self.camera is None
        if self.camera.CounterEventSource.is_implemented() and self.camera.CounterEventSource.is_writable(): # type: ignore
            self.camera.CounterEventSource.set(gx.GxCounterEventSourceEntry.LINE2) # type: ignore
        else:
            MAIN_LOG.log("CounterEventSource is not implemented or not writable")

        if self.camera.CounterReset.is_implemented(): # type: ignore
            self.camera.CounterReset.send_command() # type: ignore
        else:
            MAIN_LOG.log("CounterReset is not implemented")

    def set_line3_to_strobe(self):
        assert not self.camera is None
        # self.camera.StrobeSwitch.set(gx.GxSwitchEntry.ON)
        self.camera.LineSelector.set(gx.GxLineSelectorEntry.LINE3)
        self.camera.LineMode.set(gx.GxLineModeEntry.OUTPUT)
        self.camera.LineSource.set(gx.GxLineSourceEntry.STROBE)

    def set_line3_to_exposure_active(self):
        assert not self.camera is None
        # self.camera.StrobeSwitch.set(gx.GxSwitchEntry.ON)
        self.camera.LineSelector.set(gx.GxLineSelectorEntry.LINE3)
        self.camera.LineMode.set(gx.GxLineModeEntry.OUTPUT)
        self.camera.LineSource.set(gx.GxLineSourceEntry.EXPOSURE_ACTIVE)

    