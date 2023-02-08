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
        self.queue:Queue = Queue(64) # max this many items in the queue
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
        if image.dtype == np.uint16 and file_format != ImageFormat.TIFF_COMPRESSED:
            file_format=ImageFormat.TIFF

        # need to use tiff when saving 16 bit images
        if file_format in (ImageFormat.TIFF_COMPRESSED,ImageFormat.TIFF):
            if file_format==ImageFormat.TIFF_COMPRESSED:
                tifffile.imwrite(path + '.tiff',image,compression=tifffile.COMPRESSION.LZW) # lossless and should be widely supported
            else:
                tifffile.imwrite(path + '.tiff',image) # takes 7ms
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
        if self.stop_signal_received:
            print('! critical - attempted to save image even though stop signal was received!')
        try:
            self.queue.put_nowait([path,image,file_format])
        except:
            # if putting in image in there fails, try again but wait for a free slot this time
            self.queue.put([path,image,file_format])

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
