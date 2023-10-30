# qt libraries
from qtpy.QtCore import QObject, Signal # type: ignore

import control.utils as utils
from control._def import *

from queue import Queue, Empty
from threading import Thread, Lock
import time
import numpy as np
from datetime import datetime
import os
import numpy

import imageio as iio
import tifffile

from typing import Optional, List, Union, Tuple
from control.typechecker import TypecheckFunction

class ImageSaver(QObject):

    stop_recording = Signal()

    @TypecheckFunction
    def __init__(self,image_format:ImageFormat=Acquisition.IMAGE_FORMAT):
        QObject.__init__(self)
        self.base_path:str = './'
        self.experiment_ID:str = ''
        self.image_format:ImageFormat = image_format
        self.max_num_image_per_folder:int = 1000
        self.queue_size_max=256 # max this many items in the queue
        self.queue:Queue = Queue(self.queue_size_max)
        self.image_lock:Lock = Lock()
        self.stop_signal_received:bool = False
        self.thread = Thread(target=self.process_queue) # type: ignore
        self.thread.start()
        self.counter:int = 0
        self.recording_start_time:float = 0.0
        self.recording_time_limit:float = -1.0

    @TypecheckFunction
    def path_from(base_path:str,experiment_ID:str,folder_ID:str,file_ID:str,frame_ID:str)->str:
        p=os.path.join(base_path,experiment_ID,str(folder_ID),str(file_ID) + '_' + str(frame_ID))
        return p

    @TypecheckFunction
    def save_image(path:str,image:numpy.ndarray,file_format:ImageFormat):
        # need to use tiff when saving 16 bit images
        if image.dtype == np.uint16 and file_format != ImageFormat.TIFF_COMPRESSED:
            file_format=ImageFormat.TIFF

        # use tifffile to save tiff images
        if file_format in (ImageFormat.TIFF_COMPRESSED,ImageFormat.TIFF):
            if file_format==ImageFormat.TIFF_COMPRESSED:
                tifffile.imwrite(path + '.tiff',image,compression=tifffile.COMPRESSION.LZW) # lossless and should be widely supported
            else:
                tifffile.imwrite(path + '.tiff',image) # takes 7ms
        # use imageio to save other formats
        else:
            assert file_format==ImageFormat.BMP
            iio.imwrite(path + '.bmp',image)

    @TypecheckFunction
    def process_queue(self):
        while True:
            # process the queue
            try:
                [path,image,file_format] = self.queue.get(timeout=0.1)
                self.image_lock.acquire(True)

                # this can throw if the package that is required for the compression method is not installed, in which case this queue deadlocks because self.image_lock has been acquired, but not released
                ImageSaver.save_image(path,image,file_format)

                self.counter = self.counter + 1
                self.queue.task_done()

                self.image_lock.release()
            except Empty:
                # if queue is empty, and signal was received, terminate the thread
                if self.stop_signal_received:
                    return
        
    @TypecheckFunction
    def enqueue(self,path:str,image:numpy.ndarray,file_format:ImageFormat):
        log_msg=f"submitting image {path} to storage queue ({self.queue.qsize()}/{self.queue_size_max} slots in queue occupied)"
        MAIN_LOG.log(log_msg)

        if self.stop_signal_received:
            MAIN_LOG.log('! critical - attempted to save image even though stop signal was received!')
        
        try:
            self.queue.put_nowait([path,image,file_format])
        except:
            storage_on_device=get_storage_size_in_directory(path)
            free_space_gb=storage_on_device.free_space_bytes/1024**3
            total_space_gb=storage_on_device.total_space_bytes/1024**3

            storage_on_self=get_storage_size_in_directory(".")
            self_free_space_gb=storage_on_self.free_space_bytes/1024**3
            self_total_space_gb=storage_on_self.total_space_bytes/1024**3

            log_msg=f"warning - image saver queue is full, waiting for free slot to submit {path}. (on target storage {free_space_gb:.3f}/{total_space_gb:.3f}GB are currently available. on this computer {self_free_space_gb:.3f}/{self_total_space_gb:.3f}GB are available.)"
            MAIN_LOG.log(log_msg)

            # if putting in image in there fails initially, try again but wait for a free slot this time
            self.queue.put([path,image,file_format])
            
            # log this incident properly, to be able to trace if submitting has worked again later, and when
            log_msg=f"warning - submitted {path} to previously full storage queue"
            MAIN_LOG.log(log_msg)

    @TypecheckFunction
    def set_base_path(self,path:str):
        self.base_path = path

    @TypecheckFunction
    def set_recording_time_limit(self,time_limit:float):
        self.recording_time_limit = time_limit

    @TypecheckFunction
    def close(self):
        self.queue.join()
        self.stop_signal_received = True
        self.thread.join()
