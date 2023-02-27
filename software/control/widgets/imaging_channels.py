from typing import Optional, Callable, List, Dict, Tuple
from enum import Enum
import time

from qtpy.QtCore import Qt, QEvent
from qtpy.QtWidgets import QMainWindow, QWidget, QSizePolicy, QApplication

import pyqtgraph as pg

from PIL import ImageEnhance, Image

from control._def import MACHINE_CONFIG, TriggerMode, WELLPLATE_NAMES, WellplateFormatPhysical, WELLPLATE_FORMATS, Profiler
TRIGGER_MODES_LIST=list(TriggerMode)
from control.gui import ObjectManager, HBox, VBox, TabBar, Tab, Button, Dropdown, Label, FileDialog, FILTER_JSON, BlankWidget, Dock, SpinBoxDouble, SpinBoxInteger, Checkbox, Grid, GridItem, flatten, format_seconds_nicely
from control.core import Core, ReferenceFile, CameraWrapper
from control.core.configuration import Configuration, ConfigurationManager
import control.widgets as widgets
from control.widgets import ComponentLabel
from control.typechecker import TypecheckFunction

import numpy

BRIGHTNESS_ADJUST_MIN:float=0.1
BRIGHTNESS_ADJUST_MAX:float=5.0

CONTRAST_ADJUST_MIN:float=0.1
CONTRAST_ADJUST_MAX:float=5.0

FPS_MIN=1.0
FPS_MAX=30.0 # documentation for MER2-1220-32U3M-W90 says 32.5 fps is max, but we likely will never reach that with the manual trigger method that we use
MIN_CHANNEL_Z_OFFSET_UM=-50.0 # real limit is about +-150
MAX_CHANNEL_Z_OFFSET_UM= 50.0 # real limit is about +-150

IMAGE_ADJUST_BRIGHTNESS_TOOLTIP="Image brightness adjustment factor.\nThis factor is used to artificially brighten the image displayed in the single image view.\nThis is not applied to images displayed during acqusition, and also not to images saved."
IMAGE_ADJUST_CONTRAST_TOOLTIP="Image contrast adjustment factor.\nThis factor is used to artificially enhance the contrast of the image displayed in the single image view.\nThis is not applied to images displayed during acqusition, and also not to images saved."

CHANNEL_COLORS={
    0:"grey", # bf led full
    1:"grey", # bf led left half
    2:"grey", # bf led right half
    15:"darkRed", # 730
    13:"red", # 638
    14:"green", # 561
    12:"blue", # 488
    11:"purple", # 405
}

class ImagingChannels:
    live_display:widgets.ImageDisplayWindow
    live_config:QWidget
    channel_display:widgets.ImageArrayDisplayWindow
    channel_config:QWidget

    def __init__(self,
        configuration_manager:ConfigurationManager,
        camera_wrapper:CameraWrapper,

        on_live_status_changed:Optional[Callable[[],bool]]=None,
        on_snap_status_changed:Optional[Callable[[],bool]]=None,
        move_to_offset:Optional[Callable[[float,],None]]=None,

        get_current_position_xy_mm:Optional[Callable[[],Tuple[float,float,WellplateFormatPhysical]]]=None,
    ):
        self.configuration_manager = configuration_manager
        self.camera_wrapper=camera_wrapper
        self.camera=camera_wrapper.camera

        self.on_live_status_changed=on_live_status_changed
        self.on_snap_status_changed=on_snap_status_changed
        self.move_to_offset=move_to_offset
        self.get_current_position_xy_mm=get_current_position_xy_mm

        self.interactive_widgets=ObjectManager()

        self.channel_display=widgets.ImageArrayDisplayWindow(self.configuration_manager)

        self.imaging_mode_config_managers:Dict[int,Configuration]=dict()

        imaging_modes_widget_list=[]
        imaging_modes_wide_widgets=[]
        for config_num,config in enumerate(self.configuration_manager.configurations):
            config_manager=ObjectManager()

            imaging_modes_wide_widgets.extend([
                GridItem(
                    Label(config.name,tooltip=config.automatic_tooltip(),text_color=CHANNEL_COLORS[config.illumination_source]).widget,
                    row=config_num*2,colSpan=2
                ),
                GridItem(
                    config_manager.snap == Button(ComponentLabel.BTN_SNAP_LABEL,tooltip=ComponentLabel.BTN_SNAP_TOOLTIP,
                        on_clicked=lambda btn_state,c=config: self.snap_single(btn_state,config=self.configuration_manager.config_by_name(c.name))
                    ).widget,
                    row=config_num*2,column=2,colSpan=2
                )
            ])

            imaging_modes_widget_list.extend([
                [
                    GridItem(None,colSpan=4),
                    Label(ComponentLabel.ILLUMINATION_LABEL,tooltip=ComponentLabel.ILLUMINATION_TOOLTIP).widget,
                    config_manager.illumination_strength == SpinBoxDouble(
                        minimum=0.1,maximum=100.0,step=0.1,
                        default=config.illumination_intensity,
                        tooltip=ComponentLabel.ILLUMINATION_TOOLTIP,
                        on_valueChanged=[
                            lambda val,c=config: self.configuration_manager.config_by_name(c.name).set_illumination_intensity(val),
                            self.configuration_manager.save_configurations,
                        ]
                    ).widget,
                ],
                [   
                    Label(ComponentLabel.EXPOSURE_TIME_LABEL,tooltip=ComponentLabel.EXPOSURE_TIME_TOOLTIP).widget,
                    config_manager.exposure_time == SpinBoxDouble(
                        minimum=self.camera.EXPOSURE_TIME_MS_MIN,
                        maximum=self.camera.EXPOSURE_TIME_MS_MAX,step=1.0,
                        default=config.exposure_time_ms,
                        tooltip=ComponentLabel.EXPOSURE_TIME_TOOLTIP,
                        on_valueChanged=[
                            lambda val,c=config: self.configuration_manager.config_by_name(c.name).set_exposure_time(val),
                            self.configuration_manager.save_configurations,
                        ]
                    ).widget,
                    Label(ComponentLabel.ANALOG_GAIN_LABEL,tooltip=ComponentLabel.ANALOG_GAIN_TOOLTIP).widget,
                    config_manager.analog_gain == SpinBoxDouble(
                        minimum=0.0,maximum=24.0,step=0.1,
                        default=config.analog_gain,
                        tooltip=ComponentLabel.ANALOG_GAIN_TOOLTIP,
                        on_valueChanged=[
                            lambda val,c=config: self.configuration_manager.config_by_name(c.name).set_analog_gain(val),
                            self.configuration_manager.save_configurations,
                        ]
                    ).widget,
                    Label(ComponentLabel.CHANNEL_OFFSET_LABEL,tooltip=ComponentLabel.CHANNEL_OFFSET_TOOLTIP).widget,
                    config_manager.z_offset == SpinBoxDouble(
                        minimum=MIN_CHANNEL_Z_OFFSET_UM,maximum=MAX_CHANNEL_Z_OFFSET_UM,step=0.1,
                        default=config.channel_z_offset,
                        tooltip=ComponentLabel.CHANNEL_OFFSET_TOOLTIP,
                        on_valueChanged=[
                            lambda val,c=config: self.configuration_manager.config_by_name(c.name).set_offset(val),
                            self.configuration_manager.save_configurations,
                        ]
                    ).widget,
                ]
            ])

            self.imaging_mode_config_managers[config.mode_id]=config_manager

        def create_snap_selection_popup(
            configuration_manager,
            channel_included_in_snap_all_flags,
            parent,
        ):
            somewidget=QMainWindow(parent)

            vbox_widgets=[
                Label("Tick the channels you want to image.\n(this menu will not initiate imaging)")
            ]

            for config_i,config in enumerate(configuration_manager.configurations):
                def toggle_selection(i):
                    channel_included_in_snap_all_flags[i]=not channel_included_in_snap_all_flags[i]

                vbox_widgets.append(Checkbox(config.name,checked=channel_included_in_snap_all_flags[config_i],on_stateChanged=lambda _btn,i=config_i:toggle_selection(i)))
                            
            somewidget.setCentralWidget(VBox(*vbox_widgets).widget)
            somewidget.show()

        self.channel_included_in_snap_all_flags=[True for c in self.configuration_manager.configurations]

        self.snap_channels=HBox(
            self.interactive_widgets.snap_all_button == Button(
                ComponentLabel.BTN_SNAP_ALL_LABEL,
                tooltip=ComponentLabel.BTN_SNAP_ALL_TOOLTIP,
                on_clicked=self.snap_selected
            ).widget,
            self.interactive_widgets.snap_all_channel_selection == Button(
                ComponentLabel.BTN_SNAP_ALL_CHANNEL_SELECT_LABEL,
                tooltip=ComponentLabel.BTN_SNAP_ALL_CHANNEL_SELECT_TOOLTIP,
                on_clicked=lambda _btn:create_snap_selection_popup(
                    configuration_manager=self.configuration_manager,
                    channel_included_in_snap_all_flags=self.channel_included_in_snap_all_flags,
                    parent=self.channel_config,
                )
            ).widget,
            self.interactive_widgets.snap_all_with_offset_checkbox == Checkbox(
                label=ComponentLabel.BTN_SNAP_ALL_OFFSET_CHECKBOX_LABEL,
                tooltip=ComponentLabel.BTN_SNAP_ALL_OFFSET_CHECKBOX_TOOLTIP
            ).widget,

            with_margins=False,
        ).widget
        self.channel_config=Dock(
            Grid(
                *flatten([
                    imaging_modes_widget_list,
                    imaging_modes_wide_widgets
                ])
            ).widget,
            "Imaging mode settings"
        ).widget
        self.live_display=widgets.ImageDisplayWindow()
        self.live_config=Dock(
            VBox(
                self.interactive_widgets.histogram == pg.GraphicsLayoutWidget(show=True, title="Basic plotting examples"),
                self.interactive_widgets.imageEnhanceWidget == HBox(
                    HBox(
                        Label("View Brightness:",tooltip=IMAGE_ADJUST_BRIGHTNESS_TOOLTIP),
                        self.interactive_widgets.imageBrightnessAdjust == SpinBoxDouble(
                            tooltip=IMAGE_ADJUST_BRIGHTNESS_TOOLTIP,
                            minimum=BRIGHTNESS_ADJUST_MIN,
                            maximum=BRIGHTNESS_ADJUST_MAX,
                            default=1.0,
                            step=0.1,
                            on_valueChanged=lambda _new_value:self.display_last_single_image(),
                        ).widget
                    ).layout,
                    HBox(
                        Label("View Contrast:",tooltip=IMAGE_ADJUST_CONTRAST_TOOLTIP),
                        self.interactive_widgets.imageContrastAdjust == SpinBoxDouble(
                            tooltip=IMAGE_ADJUST_CONTRAST_TOOLTIP,
                            minimum=CONTRAST_ADJUST_MIN,
                            maximum=CONTRAST_ADJUST_MAX,
                            default=1.0,
                            step=0.1,
                            on_valueChanged=lambda _new_value:self.display_last_single_image(),
                        ).widget
                    ).layout,
                    self.interactive_widgets.histogramLogScaleCheckbox == Checkbox(
                        label="Histogram Log scale",
                        checked=Qt.Checked,
                        tooltip="Display Y-Axis of the histogram with a logrithmic scale? (uses linear scale if disabled/unchecked)",
                        on_stateChanged=lambda _btn:self.display_last_single_image(),
                    ).widget,
                ).widget,
                HBox(
                    self.interactive_widgets.live_button == Button(ComponentLabel.LIVE_BUTTON_IDLE_TEXT,checkable=True,checked=False,tooltip=ComponentLabel.LIVE_BUTTON_TOOLTIP,on_clicked=self.toggle_live).widget,
                    self.interactive_widgets.live_channel_dropdown == Dropdown(items=[config.name for config in self.configuration_manager.configurations],current_index=0,tooltip="Go live in this channel when clicking the button on the left.").widget,
                    Label("max. FPS",tooltip=ComponentLabel.FPS_TOOLTIP),
                    self.interactive_widgets.live_fps == SpinBoxDouble(minimum=FPS_MIN,maximum=FPS_MAX,step=0.1,default=5.0,num_decimals=1,tooltip=ComponentLabel.FPS_TOOLTIP).widget,
                ),
            ).widget,
            "Live Imaging"
        ).widget

        self.interactive_widgets.histogram.view=self.interactive_widgets.histogram.addViewBox()

        self.last_single_displayed_image_image:Optional[numpy.ndarray]=None
        self.last_single_displayed_image_config:Optional[Configuration]=None

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.snap_channels,
            self.channel_config,

            self.interactive_widgets.imageEnhanceWidget,
            self.interactive_widgets.live_button,
            self.interactive_widgets.live_channel_dropdown,
            self.interactive_widgets.live_fps,
        ]
    
    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        for widget in self.get_all_interactive_widgets():
            if not widget in exceptions:
                widget.setEnabled(set_enabled)
    
    def set_channel_configurations(self,new_configs:List[Configuration]):
        """
        load new configurations
        
        this just overwrites the settings for existing configurations, it does not influence the order of acquisition or add/remove channels
        i.e.:
            1. if a channel exists in the program but not in the config file, it will be left unchanged
            2. if a channel does not exist in the program but does exist in the config file, it will not be loaded into the program
        """
        for config in new_configs:
            config_exists_in_program=config.mode_id in self.imaging_mode_config_managers
            if config_exists_in_program:
                self.imaging_mode_config_managers[config.mode_id].illumination_strength.setValue(config.illumination_intensity)
                self.imaging_mode_config_managers[config.mode_id].exposure_time.setValue(config.exposure_time_ms)
                self.imaging_mode_config_managers[config.mode_id].analog_gain.setValue(config.analog_gain)
                self.imaging_mode_config_managers[config.mode_id].z_offset.setValue(config.channel_z_offset)

            overwrote_present_config=False
            for present_config in self.configuration_manager.configurations:
                if present_config.mode_id==config.mode_id:
                    present_config.illumination_intensity=config.illumination_intensity
                    present_config.exposure_time_ms=config.exposure_time_ms
                    present_config.analog_gain=config.analog_gain
                    present_config.channel_z_offset=config.channel_z_offset

                    overwrote_present_config=True
                    break

            assert config_exists_in_program==overwrote_present_config

            if not overwrote_present_config:
                print("! warning (?) - could not load imaging channel {config.name} from a config file because it does not exist in the program. (this should not happen.)")


    def get_channel_configurations(self)->List[Configuration]:
        return self.configuration_manager.configurations

    def toggle_live(self,btn_pressed):
        if btn_pressed:
            if not self.on_live_status_changed is None:
                self.on_live_status_changed(True)

            self.stop_requested=False

            channel_index=self.interactive_widgets.live_channel_dropdown.currentIndex()
            live_config=self.configuration_manager.configurations[channel_index]

            max_fps=self.interactive_widgets.live_fps.value()
            min_time_between_images=1.0/max_fps

            last_image_time=0.0
            with self.camera_wrapper.ensure_streaming():
                while not self.stop_requested:
                    time_since_last_image=time.monotonic()-last_image_time
                    while time_since_last_image<min_time_between_images:
                        time.sleep(5e-3)
                        QApplication.processEvents()
                        time_since_last_image=time.monotonic()-last_image_time

                    last_image_time=time.monotonic()
                    self.snap_single(_btn_state=None,config=live_config,control_snap_status=False)
                    QApplication.processEvents()

            if not self.on_live_status_changed is None:
                self.on_live_status_changed(False)
        else:
            self.stop_requested=True

    def snap_selected(self,_btn_state,with_offset_verride:Optional[bool]=None):
        self.on_snap_status_changed(True)

        if not with_offset_verride is None:
            with_offset=with_offset_verride
        else:
            with_offset=self.interactive_widgets.snap_all_with_offset_checkbox.checkState()==Qt.Checked
            
        with self.camera_wrapper.ensure_streaming():
            for config_i,config in enumerate(self.configuration_manager.configurations):
                if self.channel_included_in_snap_all_flags[config_i]:
                    image=self.snap_single(_btn_state=None,config=config,display_single=True,with_offset=with_offset,control_snap_status=False)
                    self.channel_display.display_image(image,channel_index=config.illumination_source)

        self.on_snap_status_changed(False)

    def snap_single(self,_btn_state,config:Configuration,profiler:Optional[Profiler]=None,display_single:bool=True,with_offset:bool=False,control_snap_status:bool=True)->numpy.ndarray:
        with Profiler("do_snap",parent=profiler) as dosnapprof:
            if control_snap_status:
                self.on_snap_status_changed(True)

            if with_offset and not self.move_to_offset is None:
                self.move_to_offset(config.channel_z_offset)
            image=self.camera_wrapper.live_controller.snap(config=config,profiler=dosnapprof)
            self.last_single_displayed_image_image=image
            self.last_single_displayed_image_config=config

        if display_single:
            self.display_last_single_image(profiler=profiler)

        if control_snap_status:
            self.on_snap_status_changed(False)

        return image
    
    def display_last_single_image(self,profiler:Optional[Profiler]=None):
        if self.last_single_displayed_image_image is None:
            return
        
        with Profiler("display",parent=profiler):
            processed_image=self.last_single_displayed_image_image

            # calculate histogram of image pixel values
            preserve_existing_histogram=False
            histogram_color="white"

            max_value=numpy.ma.minimum_fill_value(processed_image) # yes, minimum_fill_size returns maximum value (returns inf for float!)

            bins=numpy.linspace(0,max_value,129,dtype=processed_image.dtype)
            hist,bins=numpy.histogram(processed_image,bins=bins)
            hist=hist.astype(numpy.float32)
            use_histogram_log_scale=self.interactive_widgets.histogramLogScaleCheckbox.checkState()==Qt.Checked
            if use_histogram_log_scale:
                hist_nonzero_mask=hist!=0
                hist[hist_nonzero_mask]=numpy.log(hist[hist_nonzero_mask])
            hist=hist/hist.max() # normalize to [0;1]

            self.interactive_widgets.histogram.view.setLimits(
                xMin=0,
                xMax=max_value,
                yMin=0.0,
                yMax=1.0,
                minXRange=bins[4],
                maxXRange=bins[-1],
                minYRange=1.0,
                maxYRange=1.0,
            )
            self.interactive_widgets.histogram.view.setRange(xRange=(0,max_value))

            plot_kwargs={'x':bins[:-1],'y':hist,'pen':pg.mkPen(color=histogram_color)}
            try:
                if not preserve_existing_histogram:
                    self.interactive_widgets.histogram.plot_data.clear()
                self.interactive_widgets.histogram.plot_data.plot(**plot_kwargs)
            except:
                self.interactive_widgets.histogram.plot_data=self.interactive_widgets.histogram.addPlot(0,0,title="Histogram",viewBox=self.interactive_widgets.histogram.view,**plot_kwargs)
                self.interactive_widgets.histogram.plot_data.hideAxis("left")

            # enhance image brightness and contrast
            brightness_value=self.interactive_widgets.imageBrightnessAdjust.value()
            contrast_value=self.interactive_widgets.imageContrastAdjust.value()

            if brightness_value!=1.0 or contrast_value!=1.0:
                pil_image=Image.fromarray(processed_image) # requires image to be uint8

                # change brightness
                if brightness_value!=1.0:
                    brightness_enhancer = ImageEnhance.Brightness(pil_image)
                    pil_image=brightness_enhancer.enhance(brightness_value)

                # change contrast
                if contrast_value!=1.0:
                    contrast_enhancer = ImageEnhance.Contrast(pil_image)
                    pil_image=contrast_enhancer.enhance(contrast_value)

                processed_image=numpy.asarray(pil_image) # numpy.array could also be used, but asarray does not copy the image data (read only view)

            if self.last_single_displayed_image_image is None:
                self.live_display.display_image(processed_image)
                return
            
            image_name_str=self.last_single_displayed_image_config.name

            current_x_mm,current_y_mm,current_wellplate_format=self.get_current_position_xy_mm()
            well_coordinates=current_wellplate_format.pos_mm_to_well_index(current_x_mm,current_y_mm)
            if not well_coordinates is None:
                image_name_str+=" inside well "+current_wellplate_format.well_index_to_name(*well_coordinates,check_valid=False)
                
            self.live_display.display_image(processed_image,name=image_name_str)

