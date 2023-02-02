# set QT_API environment variable
import os 
os.environ["QT_API"] = "pyqt5"

from enum import Enum

from qtpy.QtWidgets import QWidget
import pyqtgraph.dockarea as dock

class ComponentLabel(str,Enum):
    LIVE_BUTTON_IDLE_TEXT="Start Live"
    LIVE_BUTTON_RUNNING_TEXT="Stop Live"
    LIVE_BUTTON_TOOLTIP="""Start/Stop live image view

    Records images multiple times per second, up to the specified maximum FPS (to the right).

    Useful for manual investigation of a plate and/or imaging settings.

    Note that this can lead to strong photobleaching. Consider using the Snap button instead.
    """
    BTN_SNAP_LABEL="Snap"
    BTN_SNAP_TOOLTIP="""
    Take a single image in the selected channel.
    
    The image will not be saved, just displayed."""
    BTN_SNAP_ALL_LABEL="Snap selection"
    BTN_SNAP_ALL_TOOLTIP="""
    Take one image in all channels and display them in the multi-point acqusition panel.
    
    The images will not be saved."""
    BTN_SNAP_ALL_CHANNEL_SELECT_LABEL="Change selection"
    BTN_SNAP_ALL_CHANNEL_SELECT_TOOLTIP="Change selection of channels imaged when clicking the button on the left."
    BTN_SNAP_ALL_OFFSET_CHECKBOX_LABEL="Apply z offset"
    BTN_SNAP_ALL_OFFSET_CHECKBOX_TOOLTIP="Move to specified offset for all imaging channels. Requires laser autofocus to be initialized."

    EXPOSURE_TIME_LABEL="Exposure time:"
    EXPOSURE_TIME_TOOLTIP="""
    Exposure time is the time the camera sensor records a single image.

    Higher exposure time means more time to record light emitted from a sample, which also increases bleaching (the light source is activate as long as the camera sensor records the light).

    Range is 0.01ms to 968.0ms
    """
    ANALOG_GAIN_LABEL="Analog gain:"
    ANALOG_GAIN_TOOLTIP="""
    Analog gain increases the camera sensor sensitiviy.

    Higher gain will make the image look brighter so that a lower exposure time can be used, but also introduces more noise.

    Note that a value of zero means that a (visible) will still be recorded.

    Range is 0.0 to 24.0
    """
    CHANNEL_OFFSET_LABEL="Z Offset:"
    CHANNEL_OFFSET_TOOLTIP="""
    Channel/Light source specific Z offset used in multipoint acquisition.
    
    Can be used to focus on cell organelles in different Z planes."""
    ILLUMINATION_LABEL="Illumination:"
    ILLUMINATION_TOOLTIP="""
    Illumination %.

    Fraction of laser power used for illumination of the sample.

    Similar effect as exposure time, e.g. the signal is about the same at 50% illumination as it is at half the exposure time.

    Range is 0.1 - 100.0 %.
    """
    CAMERA_PIXEL_FORMAT_TOOLTIP="""
    Camera pixel format

    Mono8 means monochrome (grey-scale) 8bit
    Mono12 means monochrome 12bit

    More bits can capture more detail (8bit can capture 2^8 intensity values, 12bit can capture 2^12), but also increase file size.
    Due to file format restrictions, Mono12 takes up twice the storage of Mono8 (not the expected 50%).
    """

    FPS_TOOLTIP="""
    Maximum number of frames per second that are recorded while live.

    The actual number of recorded frames per second may be smaller because of the exposure time, e.g. 5 images with 300ms exposure time each don't fit into a single second.
    """
    BTN_SAVE_CONFIG_LABEL="save config to file"
    BTN_SAVE_CONFIG_TOOLTIP="save settings related to all imaging modes/channels in a new file (this will open a window where you can specify the location to save the config file)"
    BTN_LOAD_CONFIG_LABEL="load config from file"
    BTN_LOAD_CONFIG_TOOLTIP="load settings related to all imaging modes/channels from a file (this will open a window where you will specify the file to load)"
    CONFIG_FILE_LAST_PATH_LABEL="config. file:"
    CONFIG_FILE_LAST_PATH_TOOLTIP="""
    Configuration file that was loaded last.

    If no file has been manually loaded, this will show the path to the default configuration file where the currently displayed settings are always saved.
    If a file has been manually loaded at some point, the last file that was loaded will be displayed.

    An asterisk (*) will be displayed after the filename if the settings have been changed since a file has been loaded.

    These settings are continuously saved into the default configuration file and restored when the program is started up again, they do NOT automatically overwrite the last configuration file that was loaded.
    """


from .autofocus import AutofocusWidget
from .live_control import LiveControlWidget
from .multi_point import MultiPointWidget
from .navigation import NavigationWidget
from .well import WellWidget
from .image_display import ImageDisplay, ImageDisplayWindow, ImageArrayDisplayWindow
from .imaging_channels import ImagingChannels

from typing import Optional, Any