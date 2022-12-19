# qt libraries
from qtpy.QtCore import Qt, QEvent, Signal
from qtpy.QtWidgets import QMainWindow, QTabWidget, QPushButton, QComboBox, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QDesktopWidget, QSlider, QCheckBox, QWidget, QApplication

import numpy

# app specific libraries
import control.widgets as widgets
from control.camera import Camera
import control.core as core
import control.microcontroller as microcontroller
#from control.hcs import HCSController
from control._def import *
from control.core.displacement_measurement import DisplacementMeasurementController
from control.gui import *

import pyqtgraph as pg
import pyqtgraph.dockarea as dock

from PIL import ImageEnhance, Image
import time

from control.typechecker import TypecheckFunction
from typing import Union

from tqdm import tqdm

import os

LIVE_BUTTON_IDLE_TEXT="Start Live"
LIVE_BUTTON_RUNNING_TEXT="Stop Live"
LIVE_BUTTON_TOOLTIP="""start/stop live image view

displays each image that is recorded by the camera

useful for manual investigation of a plate and/or imaging settings. Note that this can lead to strong photobleaching. Consider using the snapshot button instead (labelled 'snap')"""

BTN_SNAP_LABEL="snap"
BTN_SNAP_TOOLTIP="take single image (minimizes bleaching for manual testing)"
BTN_SNAP_ALL_LABEL="snap all"
BTN_SNAP_ALL_TOOLTIP="Take image in all channels and display them in the multi-point acqusition panel."

EXPOSURE_TIME_TOOLTIP="exposure time is the time the camera sensor records an image. Higher exposure time means more time to record light emitted from a sample, which also increases bleaching (the light source is activate as long as the camera sensor records the light)"
ANALOG_GAIN_TOOLTIP="analog gain increases the camera sensor sensitiviy. Higher gain will make the image look brighter so that a lower exposure time can be used, but also introduces more noise."
CHANNEL_OFFSET_TOOLTIP="channel specific z offset used in multipoint acquisition to focus properly in channels that are not in focus at the same time the nucleus is (given the nucleus is the channel that is used for focusing)"
ILLUMINATION_TOOLTIP="""
Illumination %.

Fraction of laser power used for illumination of the sample.

Similar effect as exposure time, e.g. the signal is about the same at 50% illumination as it is at half the exposure time.
If the signal shall be reduced, prefer reducing the exposure time rather than the illumination to reduce imaging time.

Range is 0.1 - 100.0 %.
"""

CAMERA_PIXEL_FORMAT_TOOLTIP="""
Camera pixel format

MONO8 means monochrome (grey-scale) 8bit
MONO12 means monochrome 12bit

more bits can capture more detail (8bit can capture 2^8 intensity values, 12bit can capture 2^12), but also increase file size
"""

FPS_TOOLTIP="Maximum number of frames per second that are recorded while live (capped by exposure time, e.g. 5 images with 300ms exposure time each dont fit into a single second)"

CHANNEL_COLORS={
    15:"darkRed", # 730
    13:"red", # 638
    14:"green", # 561
    12:"blue", # 488
    11:"purple", # 405
}

def seconds_to_long_time(sec:float)->str:
    hours=int(sec//3600)
    sec-=hours*3600
    minutes=int(sec//60)
    sec-=minutes*60
    return f"{hours:3}h {minutes:2}m {sec:4.1f}s"

class OctopiGUI(QMainWindow):

    @property
    def configurationManager(self)->core.ConfigurationManager:
        return self.core.configurationManager
    @property
    def streamHandler(self)->core.StreamHandler:
        return self.core.streamHandler
    @property
    def liveController(self)->core.LiveController:
        return self.core.liveController
    @property
    def navigation(self)->core.NavigationController:
        return self.core.navigation
    @property
    def autofocusController(self)->core.AutoFocusController:
        return self.core.autofocusController
    @property
    def multipointController(self)->core.MultiPointController:
        return self.core.multipointController
    @property
    def imageSaver(self)->core.ImageSaver:
        return self.core.imageSaver
    @property
    def camera(self)->Camera:
        return self.core.camera
    @property
    def focus_camera(self)->Camera:
        return self.core.focus_camera.camera
    @property
    def microcontroller(self)->microcontroller.Microcontroller:
        return self.core.microcontroller
    @property
    def configurationManager_focus_camera(self)->core.ConfigurationManager:
        return self.core.configurationManager_focus_camera
    @property
    def streamHandler_focus_camera(self)->core.StreamHandler:
        return self.core.streamHandler_focus_camera
    @property
    def liveController_focus_camera(self)->core.LiveController:
        return self.core.liveController_focus_camera
    @property
    def displacementMeasurementController(self)->DisplacementMeasurementController:
        return self.core.displacementMeasurementController
    @property
    def laserAutofocusController(self)->core.LaserAutofocusController:
        return self.core.laserAutofocusController

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.core=core.Core(home=not bool(int(os.environ.get('skip_homing') or 0))) # var is expected to be '1' to skip homing, '0' to not skip it. environment variables are strings though, and bool() cannot parse strings, int() can though. if an env var does not exist, os.environ.get() returns None, so fall back to case where homing is not skipped.

        self.named_widgets=ObjectManager()

        self.streamHandler.packet_image_to_write.connect(self.imageSaver.enqueue)
        self.streamHandler.signal_new_frame_received.connect(self.liveController.on_new_frame)

        # load window
        self.imageDisplayWindow = widgets.ImageDisplayWindow(draw_crosshairs=True)
        self.imageArrayDisplayWindow = widgets.ImageArrayDisplayWindow(self.configurationManager,window_title="HCS microscope control")

        default_well_plate=WELLPLATE_NAMES[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT]

        # load widgets
        self.imageDisplay           = widgets.ImageDisplay()
        self.streamHandler.image_to_display.connect(self.imageDisplay.enqueue)
        self.wellSelectionWidget    = widgets.WellSelectionWidget(MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT)
        self.navigationWidget       = widgets.NavigationWidget(self.core,gui=self,widget_configuration=default_well_plate)
        self.autofocusWidget        = widgets.AutoFocusWidget(self.core,gui=self)
        self.multiPointWidget       = widgets.MultiPointWidget(self.core,gui=self,start_experiment=self.start_experiment,abort_experiment=self.abort_experiment)
        self.navigationViewer       = widgets.NavigationViewer(sample=default_well_plate)

        self.imaging_mode_config_managers={}

        imaging_modes_widget_list=[]
        imaging_modes_wide_widgets=[]
        for config_num,config in enumerate(self.configurationManager.configurations):
            config_manager=ObjectManager()

            imaging_modes_wide_widgets.append(GridItem(Label(config.name,tooltip=config.automatic_tooltip,text_color=CHANNEL_COLORS[config.illumination_source]).widget,config_num*2,0,1,2))
            imaging_modes_wide_widgets.append(GridItem(config_manager.snap == Button(BTN_SNAP_LABEL,tooltip=BTN_SNAP_TOOLTIP,on_clicked=lambda btn_state,config=config:self.snap_single(btn_state,config)).widget,config_num*2,2,1,2))

            imaging_modes_widget_list.extend([
                [
                    *([None]*4),
                    Label("illumination:",tooltip=ILLUMINATION_TOOLTIP).widget,
                    config_manager.illumination_strength == SpinBoxDouble(
                        minimum=0.1,maximum=100.0,step=0.1,
                        default=config.illumination_intensity,
                        tooltip=ILLUMINATION_TOOLTIP,
                        on_valueChanged=[
                            config.set_illumination_intensity,
                            self.configurationManager.save_configurations,
                            lambda btn:self.set_illumination_config_path_display(btn,set_config_changed=True),
                        ]
                    ).widget,
                ],
                [   
                    Label("exposure time:",tooltip=EXPOSURE_TIME_TOOLTIP).widget,
                    config_manager.exposure_time == SpinBoxDouble(
                        minimum=self.liveController.camera.EXPOSURE_TIME_MS_MIN,
                        maximum=self.liveController.camera.EXPOSURE_TIME_MS_MAX,step=1.0,
                        default=config.exposure_time,
                        tooltip=EXPOSURE_TIME_TOOLTIP,
                        on_valueChanged=[
                            config.set_exposure_time,
                            self.configurationManager.save_configurations,
                            lambda btn:self.set_illumination_config_path_display(btn,set_config_changed=True),
                        ]
                    ).widget,
                    Label("gain:",tooltip=ANALOG_GAIN_TOOLTIP).widget,
                    config_manager.analog_gain == SpinBoxDouble(
                        minimum=0.0,maximum=24.0,step=0.1,
                        default=config.analog_gain,
                        tooltip=ANALOG_GAIN_TOOLTIP,
                        on_valueChanged=[
                            config.set_analog_gain,
                            self.configurationManager.save_configurations,
                            lambda btn:self.set_illumination_config_path_display(btn,set_config_changed=True),
                        ]
                    ).widget,
                    Label("offset:",tooltip=CHANNEL_OFFSET_TOOLTIP).widget,
                    config_manager.z_offset == SpinBoxDouble(
                        minimum=-30.0,maximum=30.0,step=0.1,
                        default=config.channel_z_offset,
                        tooltip=CHANNEL_OFFSET_TOOLTIP,
                        on_valueChanged=[
                            config.set_offset,
                            self.configurationManager.save_configurations,
                            lambda btn:self.set_illumination_config_path_display(btn,set_config_changed=True),
                        ]
                    ).widget,
                ]
            ])

            self.imaging_mode_config_managers[config.id]=config_manager

        self.add_image_inspection()

        self.named_widgets.laserAutofocusControlWidget == widgets.LaserAutofocusControlWidget(self.laserAutofocusController)
        self.named_widgets.laserAutofocusControlWidget.btn_set_reference.clicked.connect(lambda _btn_state:self.multiPointWidget.checkbox_laserAutofocs.setDisabled(False))

        self.named_widgets.live == ObjectManager()
        self.imagingModes=VBox(
            # snap and channel config section
            HBox(
                self.named_widgets.snap_all_button == Button(BTN_SNAP_ALL_LABEL,tooltip=BTN_SNAP_ALL_TOOLTIP,on_clicked=self.snap_all),
                self.named_widgets.snap_all_with_offset_checkbox == Checkbox(label="incl. offset",tooltip="not implemented yet.",enabled=False),#move to channel-specific offset from reference plane on snap"),
            ),

            Label(""),
            Grid(*flatten([
                imaging_modes_widget_list,
                imaging_modes_wide_widgets
            ])),

            # config save/load section
            Label(""),
            HBox(
                self.named_widgets.save_config_button == Button("save config to file",tooltip="save settings related to all imaging modes/channels in a new file (this will open a window where you can specify the location to save the config file)",on_clicked=self.save_illumination_config),
                self.named_widgets.load_config_button == Button("load config from file",tooltip="load settings related to all imaging modes/channels from a file (this will open a window where you will specify the file to load)",on_clicked=self.load_illumination_config),
            ),
            HBox(
                Label("config. file:",tooltip="configuration file that was loaded last. If no file has been manually loaded, this will show the path to the default configuration file where the currently displayed settings are always saved. If a file has been manually loaded at some point, the last file that was loaded will be displayed. An asterisk (*) will be displayed after the filename if the settings have been changed since a file has been loaded (these settings are always saved into the default configuration file and restored when the program is started up again, they do NOT automatically overwrite the last configuration file that was loaded.)"),
                self.named_widgets.last_configuration_file_path == Label("").widget,
            ),

            # numerical investigation section
            Label(""),
            Dock(self.histogramWidget,"Histogram").widget,
            self.backgroundSliderContainer,
            self.imageEnhanceWidget,

            # focus related stuff section
            Label(""),
            HBox(
                self.named_widgets.live.button == Button(LIVE_BUTTON_IDLE_TEXT,checkable=True,checked=False,tooltip=LIVE_BUTTON_TOOLTIP,on_clicked=self.toggle_live).widget,
                self.named_widgets.live.channel_dropdown == Dropdown(items=[config.name for config in self.configurationManager.configurations],current_index=0).widget,
                Label("max. FPS",tooltip=FPS_TOOLTIP),
                self.named_widgets.live.fps == SpinBoxDouble(minimum=1.0,maximum=10.0,step=0.1,default=5.0,num_decimals=1,tooltip=FPS_TOOLTIP).widget,
            ),
            Dock(self.navigationWidget,"Navigation",True).widget,

            # autofocus section
            Dock(self.named_widgets.laserAutofocusControlWidget,title="Laser AF",minimize_height=True).widget,
            Dock(self.autofocusWidget,title="Software AF",minimize_height=True).widget,
        ).widget

        self.set_illumination_config_path_display(new_path=self.configurationManager.config_filename,set_config_changed=False)

        if False:
            self.liveWidget=VBox(
                #self.named_widgets.special_widget == BlankWidget(
                #    height=300,width=300,
                #    #background_image_path="./images/384_well_plate_1509x1010.png",
                #    children=self.named_widgets.wells == [
                #        BlankWidget(
                #            height=10,width=10,
                #            background_color="red",
                #            offset_left=i*(10+5),offset_top=j*(10+5),
                #            on_mousePressEvent=lambda event,i=i,j=j: self.well_click_callback(event,i,j)
                #        )
                #        for i in range(24) for j in range(16)
                #    ]
                #),
            ).widget

        self.recordTabWidget = TabBar(
            Tab(self.multiPointWidget, "Acquisition"),
            Tab(self.imagingModes,"Setup"),
        ).widget

        clear_history_button=Button("clear history",on_clicked=self.navigationViewer.clear_imaged_positions).widget

        wellplate_types_str=list(WELLPLATE_NAMES.values())
        self.named_widgets.wellplate_selector == Dropdown(
            items=wellplate_types_str,
            current_index=wellplate_types_str.index(default_well_plate),
            on_currentIndexChanged=lambda wellplate_type_index:setattr(MACHINE_CONFIG.MUTABLE_STATE,"WELLPLATE_FORMAT",tuple(WELLPLATE_FORMATS.keys())[wellplate_type_index])
        ).widget
        # disable 6 and 24 well wellplates, because images of these plates are missing
        for wpt in [0,2]:
            item=self.named_widgets.wellplate_selector.model().item(wpt)
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled) # type: ignore

        self.navigationViewWrapper=VBox(
            HBox( QLabel("wellplate overview"), clear_history_button, QLabel("change plate type:"), self.named_widgets.wellplate_selector ).layout,
            self.navigationViewer
        ).layout

        self.multiPointWidget.grid.layout.addWidget(self.wellSelectionWidget,5,0)
        self.multiPointWidget.grid.layout.addLayout(self.navigationViewWrapper,6,0)

        # layout widgets
        
        # transfer the layout to the central widget
        trigger_modes_list=[
            TriggerMode.SOFTWARE,
            TriggerMode.HARDWARE,
        ]
        self.centralWidget:QWidget = VBox(
            HBox(
                Label("Camera Trigger",tooltip="Camera trigger type. If you don't know this does, chances are you don't need to change it. (Hardware trigger may reduce bleaching effect slightly)"),
                self.named_widgets.trigger_mode_dropdown == Dropdown(
                    items=trigger_modes_list,
                    current_index=0,
                    on_currentIndexChanged=lambda new_index:setattr(MACHINE_CONFIG.MUTABLE_STATE,"DEFAULT_TRIGGER_MODE",trigger_modes_list[new_index])
                ),
                Label("Camera Pixel Format",tooltip="Change camera pixel format. Larger number of bits per pixel can provide finer granularity (no impact on value range) of the recorded signal, but also takes up more storage."),
                self.named_widgets.pixel_format == Dropdown(
                    items=self.core.main_camera.pixel_formats,
                    current_index=0, # default pixel format is 8 bits
                    on_currentIndexChanged=self.set_main_camera_pixel_format,
                    tooltip="",
                ),
            ),
            HBox(
                self.named_widgets.save_all_config == Button("save all config",on_clicked=self.save_all_config, enabled=False, tooltip="not implemented yet."),
                self.named_widgets.load_all_config == Button("load all config",on_clicked=self.load_all_config, enabled=False, tooltip="not implemented yet."),
            ),
            self.recordTabWidget
        ).widget
        
        desktopWidget = QDesktopWidget()
        width_min = int(0.96*desktopWidget.width())
        height_min = int(0.9*desktopWidget.height())

        # laser af section
        LASER_AUTOFOCUS_LIVE_CONTROLLER_ENABLED=True
        if LASER_AUTOFOCUS_LIVE_CONTROLLER_ENABLED:
            self.liveControlWidget_focus_camera = widgets.LiveControlWidget(self.streamHandler_focus_camera,self.liveController_focus_camera,self.configurationManager_focus_camera)
            self.imageDisplayWindow_focus = widgets.ImageDisplayWindow(draw_crosshairs=True)

            dock_laserfocus_image_display = Dock(
                widget=self.imageDisplayWindow_focus.widget,
                title='Focus Camera Image Display'
            ).widget
            dock_laserfocus_liveController = Dock(
                title='Focus Camera Controller',
                widget=VBox(
                    self.liveControlWidget_focus_camera,
                    HBox(
                        Button("measure",on_clicked=self.calibrate_displacement),
                        self.named_widgets.displacement_accuracy_granularity == SpinBoxInteger(minimum=1,maximum=20,default=7,step=1),
                        self.named_widgets.displacement_accuracy_halfrange == SpinBoxDouble(minimum=100.0,maximum=300.0,default=150.0,step=10.0),
                    ),
                    self.named_widgets.displacement_graph_widget == pg.GraphicsLayoutWidget(show=True, title="Basic plotting examples")
                ).widget,
                fixed_width=self.liveControlWidget_focus_camera.minimumSizeHint().width()
            ).widget

            laserfocus_dockArea = dock.DockArea()
            laserfocus_dockArea.addDock(dock_laserfocus_image_display)
            laserfocus_dockArea.addDock(dock_laserfocus_liveController,'right',relativeTo=dock_laserfocus_image_display)

            # connections
            self.liveControlWidget_focus_camera.update_camera_settings()

            self.streamHandler_focus_camera.image_to_display.connect(self.imageDisplayWindow_focus.display_image)
            self.laserAutofocusController.image_to_display.connect(self.imageDisplayWindow_focus.display_image)

            self.streamHandler_focus_camera.signal_new_frame_received.connect(self.liveController_focus_camera.on_new_frame)

        # make connections
        self.navigation.xPos.connect(self.navigationWidget.set_pos_x)
        self.navigation.yPos.connect(self.navigationWidget.set_pos_y)
        self.navigation.zPos.connect(self.navigationWidget.set_pos_z)
        self.navigation.signal_joystick_button_pressed.connect(self.autofocusController.autofocus)
        self.navigation.xyPos.connect(self.navigationViewer.update_current_location)

        self.imageDisplay.image_to_display.connect(self.processLiveImage) # internally calls self.imageDisplayWindow.display_image, among other things

        self.autofocusController.image_to_display.connect(self.imageDisplayWindow.display_image)

        self.multipointController.signal_register_current_fov.connect(self.navigationViewer.register_fov)

        self.wellSelectionWidget.signal_wellSelectedPos.connect(self.navigation.move_to)

        # if well selection changes, or dx/y or Nx/y change, redraw preview
        self.wellSelectionWidget.itemSelectionChanged.connect(self.on_well_selection_change)

        self.multiPointWidget.entry_deltaX.valueChanged.connect(self.on_well_selection_change)
        self.multiPointWidget.entry_deltaY.valueChanged.connect(self.on_well_selection_change)

        self.multiPointWidget.entry_NX.valueChanged.connect(self.on_well_selection_change)
        self.multiPointWidget.entry_NY.valueChanged.connect(self.on_well_selection_change)

        # image display windows
        self.imageDisplayTabs = TabBar(
            Tab(self.imageDisplayWindow.widget, "Single View"),
            Tab(self.imageArrayDisplayWindow.widget, "Multi View"),
            Tab(laserfocus_dockArea,"Laser AF Signal"),
        ).widget

        main_dockArea = dock.DockArea()
        main_dockArea.addDock(Dock(
            title='Image Display',
            widget=self.imageDisplayTabs
        ).widget)
        main_dockArea.addDock(Dock(
            title='Controls',
            widget=self.centralWidget, 
            fixed_width=width_min*0.25, stretch_x=1,stretch_y=None
        ).widget,'right')

        self.setCentralWidget(main_dockArea)
        self.setMinimumSize(width_min,height_min)

    def calibrate_displacement(self):
        half_range=self.named_widgets.displacement_accuracy_halfrange.widget.value()
        x=numpy.linspace(-half_range,half_range,50)
        y0=x.copy()
        y1=numpy.zeros_like(x)

        try:
            _=self.named_widgets.displacement_graph_widget.view
        except:
            self.named_widgets.displacement_graph_widget.view=self.named_widgets.displacement_graph_widget.addViewBox()
        try:
            _=self.named_widgets.displacement_graph_widget.plot
            self.named_widgets.displacement_graph_widget.plot.clear()
        except:
            self.named_widgets.displacement_graph_widget.plot=self.named_widgets.displacement_graph_widget.addPlot(0,0,title="displacement",viewBox=self.named_widgets.displacement_graph_widget.view)

        total_moved_distance=0.0
        with core.StreamingCamera(self.core.focus_camera.camera):
            for i,x_i in enumerate(tqdm(x)):
                if i==0:
                    move_z_distance_um=x_i
                else:
                    move_z_distance_um=x_i-x[i-1]

                total_moved_distance+=move_z_distance_um
                if i==0:
                    self.core.navigation.move_z(move_z_distance_um*1e-3-1e-2,wait_for_completion={})
                    self.core.navigation.move_z(1e-2,wait_for_completion={})
                else:
                    self.core.navigation.move_z(move_z_distance_um*1e-3,wait_for_completion={})
                    
                measured_displacement=self.core.laserAutofocusController.measure_displacement(self.named_widgets.displacement_accuracy_granularity.widget.value())
                if i==0:
                    measured_displacement=self.core.laserAutofocusController.measure_displacement(self.named_widgets.displacement_accuracy_granularity.widget.value())

                y1[i]=measured_displacement

                QApplication.processEvents()

        move_z_distance_um=-total_moved_distance
        self.core.navigation.move_z(move_z_distance_um*1e-3,wait_for_completion={})

        self.named_widgets.displacement_graph_widget.plot.plot(x=x,y=y0,pen=pg.mkPen(color="green"))
        self.named_widgets.displacement_graph_widget.plot.plot(x=x,y=y1,pen=pg.mkPen(color="orange"))
        self.named_widgets.displacement_graph_widget.plot.plot(x=x,y=y1-y0,pen=pg.mkPen(color="red"))

    def set_main_camera_pixel_format(self,pixel_format_index):
        new_pixel_format=self.core.main_camera.pixel_formats[pixel_format_index]
        self.core.main_camera.camera.set_pixel_format(new_pixel_format)

    def save_all_config(self):
        print("save_all_config")

    def load_all_config(self):
        print("load_all_config")

    # @TypecheckFunction # dont check because signal cannot yet be checked properly
    def start_experiment(self,experiment_data_target_folder:str,imaging_channel_list:List[str])->Optional[Signal]:
        self.navigationViewer.register_preview_fovs()

        well_list=self.wellSelectionWidget.currently_selected_well_indices

        af_channel=self.multipointController.autofocus_channel_name if self.multipointController.do_autofocus else None

        acquisition_thread=self.core.acquire(
            well_list,
            imaging_channel_list,
            experiment_data_target_folder,
            grid_data={
                'x':{'d':self.multipointController.deltaX,'N':self.multipointController.NX},
                'y':{'d':self.multipointController.deltaY,'N':self.multipointController.NY},
                'z':{'d':self.multipointController.deltaZ,'N':self.multipointController.NZ},
                't':{'d':self.multipointController.deltat,'N':self.multipointController.Nt},
            },
            af_channel=af_channel,
            set_num_acquisitions_callback=self.set_num_acquisitions,
            on_new_acquisition=self.on_step_completed,

            grid_mask=self.multiPointWidget.well_grid_items_selected,
            headless=False, # allow display of gui components like warning messages
        )
        
        if acquisition_thread is None:
            return None

        return acquisition_thread.finished

    def set_num_acquisitions(self,num:int):
        self.acquisition_progress=0
        self.total_num_acquisitions=num
        self.acquisition_start_time=time.monotonic()
        self.multiPointWidget.progress_bar.setValue(0)
        self.multiPointWidget.progress_bar.setMinimum(0)
        self.multiPointWidget.progress_bar.setMaximum(num)

    def on_step_completed(self,step:str):
        if step=="x": # x (in well)
            pass
        elif step=="y": # y (in well)
            pass
        elif step=="z": # z (in well)
            pass
        elif step=="t": # time
            pass
        elif step=="c": # channel
            # this is the innermost callback
            # for each one of these, one image is actually taken

            self.acquisition_progress+=1
            self.multiPointWidget.progress_bar.setValue(self.acquisition_progress)

            time_elapsed_since_start=time.monotonic()-self.acquisition_start_time
            approx_time_left=time_elapsed_since_start/self.acquisition_progress*(self.total_num_acquisitions-self.acquisition_progress)

            elapsed_time_str=seconds_to_long_time(time_elapsed_since_start)
            if self.acquisition_progress==self.total_num_acquisitions:
                self.multiPointWidget.progress_bar.setFormat(f"done. (acquired {self.total_num_acquisitions:4} images in {elapsed_time_str})")
            else:
                approx_time_left_str=seconds_to_long_time(approx_time_left)
                done_percent=int(self.acquisition_progress*100/self.total_num_acquisitions)
                progress_bar_text=f"completed {self.acquisition_progress:4}/{self.total_num_acquisitions:4} images ({done_percent:2}%) in {elapsed_time_str} (eta: {approx_time_left_str})"
                self.multiPointWidget.progress_bar.setFormat(progress_bar_text)

    def abort_experiment(self):
        self.multipointController.request_abort_aquisition()

    def well_click_callback(self,event,i,j):
        """ TODO : implement custom well selection widget """
        self.named_widgets.wells[i*16+j].setStyleSheet("QWidget {background-color: blue;}")

    def get_all_interactible_widgets(self)->list:
        ret=[
            self.named_widgets.trigger_mode_dropdown,
            self.named_widgets.pixel_format,

            #self.named_widgets.save_all_config, # currently disabled because they are not implemented
            #self.named_widgets.load_all_config, # currently disabled because they are not implemented

            self.named_widgets.snap_all_button,
            #self.named_widgets.snap_all_with_offset_checkbox, # currently disabled because they are not implemented

            self.named_widgets.save_config_button,
            self.named_widgets.load_config_button,

            self.named_widgets.live.button,
            self.named_widgets.live.channel_dropdown,
            self.named_widgets.live.fps,

            self.named_widgets.laserAutofocusControlWidget,
            self.autofocusWidget,

            self.navigationWidget,

            *(self.multiPointWidget.get_all_interactible_widgets()),

            self.named_widgets.wellplate_selector,
        ]

        for _id,manager in self.imaging_mode_config_managers.items():
            ret.append(manager.illumination_strength)
            ret.append(manager.exposure_time)
            ret.append(manager.analog_gain)
            ret.append(manager.z_offset)
            ret.append(manager.snap)

        return ret

    def set_all_interactibles_enabled(self,enable:bool,exceptions:list=[]):
        """
        set interactible state for all interactible widgets in the whole gui.
        allows certain widgets to be excluded from applying the new interactible state ('exceptions' argument).

        can be used e.g. to disable all widgets that interact with the hardware while imaging is in progress to avoid conflicts.
        """

        for widget in self.get_all_interactible_widgets():
            if not widget in exceptions:
                if isinstance(widget,QWidget):
                    widget.setEnabled(enable)
                elif isinstance(widget,HasWidget):
                    widget.widget.setEnabled(enable)
    
        QApplication.processEvents()

    def toggle_live(self,button_pressed:bool):
        """
        take images at regular time intervals in the selected channel.

        can be used e.g. to view the impact of a new z position on image focus.
        """
        if button_pressed:
            self.live_stop_requested=False

            # go live
            self.named_widgets.live.button.setText(LIVE_BUTTON_RUNNING_TEXT)

            channel_index=self.named_widgets.live.channel_dropdown.currentIndex()
            config=self.configurationManager.configurations[channel_index]
            fps=self.named_widgets.live.fps.value()

            self.set_all_interactibles_enabled(False,exceptions=[
                self.named_widgets.live.button,
                self.navigationWidget,
            ])

            with core.StreamingCamera(self.camera):
                last_imaging_time=0.0
                while True:
                    current_time=time.monotonic()
                    if current_time-last_imaging_time > 1/fps:
                        self.snap_single(_button_state=True,config=config,display_in_image_array_display=False,preserve_existing_histogram=False)
                        last_imaging_time=current_time

                    QApplication.processEvents()

                    if self.live_stop_requested:
                        # leave live
                        self.named_widgets.live.button.setText(LIVE_BUTTON_IDLE_TEXT)
                        
                        self.set_all_interactibles_enabled(True)

                        break
        else:
            self.live_stop_requested=True

    def set_illumination_config_path_display(self,_button_state:Any=None,new_path:Optional[str]=None,set_config_changed:Optional[bool]=None):
        if not set_config_changed is None:
            self.configuration_has_been_changed_since_last_load=set_config_changed
        if not new_path is None:
            self.last_loaded_configuration_file=new_path

        path_label_text=self.last_loaded_configuration_file
        if self.configuration_has_been_changed_since_last_load:
            path_label_text+=" *"
        self.named_widgets.last_configuration_file_path.setText(path_label_text)

    def save_illumination_config(self,_button_state:bool):
        """ save illumination configuration to a file (GUI callback) """

        save_path=FileDialog(mode='save',directory=MACHINE_CONFIG.DISPLAY.DEFAULT_SAVING_PATH,caption="Save current illumination config where?").run()

        if save_path!="":
            if not save_path.endswith(".json"):
                save_path=save_path+".json"
            print(f"saving config to {save_path}")
            self.configurationManager.write_configuration(save_path)

            self.set_illumination_config_path_display(new_path=save_path,set_config_changed=False)

    def load_illumination_config(self,_button_state:bool):
        """ load illumination configuration from a file (GUI callback) """

        if self.liveController.camera.is_live:
            print("! warning: cannot load illumination settings while live !")
            return
        
        load_path=FileDialog(mode='open',directory=MACHINE_CONFIG.DISPLAY.DEFAULT_SAVING_PATH,caption="Load which illumination config?",filter_type="JSON (*.json)").run()

        if load_path!="":
            print(f"loading config from {load_path}")

            self.configurationManager.read_configurations(load_path)
            for config in self.configurationManager.configurations:
                self.imaging_mode_config_managers[config.id].illumination_strength.setValue(config.illumination_intensity)
                self.imaging_mode_config_managers[config.id].exposure_time.setValue(config.exposure_time)
                self.imaging_mode_config_managers[config.id].analog_gain.setValue(config.analog_gain)
                self.imaging_mode_config_managers[config.id].z_offset.setValue(config.channel_z_offset)

            self.set_illumination_config_path_display(new_path=load_path,set_config_changed=False)

    def snap_single(self,_button_state,
        config:core.Configuration,
        display_in_image_array_display:bool=True,
        preserve_existing_histogram:bool=False,
    ):
        image=self.liveController.snap(config)
        QApplication.processEvents()
        histogram_color=CHANNEL_COLORS[config.illumination_source]
        self.processLiveImage(image,histogram_color=histogram_color,preserve_existing_histogram=preserve_existing_histogram)
        QApplication.processEvents()

        if display_in_image_array_display:
            self.imageArrayDisplayWindow.display_image(image,config.illumination_source)
            QApplication.processEvents()

    def snap_all(self,_button_state):
        with core.StreamingCamera(self.camera):
            for config in self.configurationManager.configurations:
                self.snap_single(_button_state,config,display_in_image_array_display=True,preserve_existing_histogram=True)

    def add_image_inspection(self,
        brightness_adjust_min:float=0.1,
        brightness_adjust_max:float=5.0,

        contrast_adjust_min:float=0.1,
        contrast_adjust_max:float=5.0,

        histogram_log_display_default:bool=True
    ):
        self.histogramWidget=pg.GraphicsLayoutWidget(show=True, title="Basic plotting examples")
        self.histogramWidget.view=self.histogramWidget.addViewBox()

        # add panel to change image settings
        self.imageBrightnessAdjust=HBox(
            Label("View Brightness:"),
            SpinBoxDouble(
                minimum=brightness_adjust_min,
                maximum=brightness_adjust_max,
                default=1.0,
                step=0.1,
                on_valueChanged=self.set_brightness,
            )
        ).layout
        self.imageBrightnessAdjust.value=1.0

        self.imageContrastAdjust=HBox(
            Label("View Contrast:"),
            SpinBoxDouble(
                minimum=contrast_adjust_min,
                maximum=contrast_adjust_max,
                default=1.0,
                step=0.1,
                on_valueChanged=self.set_contrast,
            )
        ).layout
        self.imageContrastAdjust.value=1.0

        self.histogram_log_scale=histogram_log_display_default
        self.histogramLogScaleCheckbox=Checkbox(
            label="Histogram Log scale",
            checked=self.histogram_log_scale*2, # convert from bool to weird tri-stateable value (i.e. 0,1,2 where 0 is unchecked, 2 is checked, and 1 is in between. if this is set to 1, the button will become to tri-stable)
            tooltip="Display Y-Axis of the histogram with a logrithmic scale? (uses linear scale if disabled/unchecked)",
            on_stateChanged=self.setHistogramLogScale,
        )

        self.imageEnhanceWidget=HBox(
            self.imageBrightnessAdjust,
            self.imageContrastAdjust,
            self.histogramLogScaleCheckbox,
        ).layout
        self.last_raw_image=None
        self.last_image_data=None

        self.backgroundSlider=QSlider(Qt.Horizontal)
        self.backgroundSlider.setTickPosition(QSlider.TicksBelow)
        self.backgroundSlider.setRange(1,255)
        self.backgroundSlider.setSingleStep(1)
        self.backgroundSlider.setTickInterval(16)
        self.backgroundSlider.valueChanged.connect(self.set_background)
        self.backgroundSlider.setValue(10)

        self.backgroundSNRValueText=QLabel("SNR: undefined")

        self.backgroundHeader=HBox( QLabel("Background"), self.backgroundSNRValueText ).layout

        self.backgroundSliderContainer=VBox(
            self.backgroundHeader,
            self.backgroundSlider
        ).layout        

    def set_background(self,new_background_value:int):
        self.backgroundSlider.value=new_background_value
        self.processLiveImage()

    @TypecheckFunction
    def setHistogramLogScale(self,state:Union[bool,int]):
        if type(state)==int:
            state=bool(state)

        self.histogram_log_scale=state
        self.processLiveImage(calculate_histogram=True)

    @TypecheckFunction
    def set_brightness(self,value:float):
        """ value<1 darkens image, value>1 brightens image """

        self.imageBrightnessAdjust.value=value

        self.processLiveImage()

    @TypecheckFunction
    def set_contrast(self,value:float):
        """ value<1 decreases image contrast, value>1 increases image contrast """

        self.imageContrastAdjust.value=value

        self.processLiveImage()

    # callback for newly acquired images in live view (that saves last live image and recalculates histogram or image view on request based on last live image)
    @TypecheckFunction
    def processLiveImage(self,
        image_data:Optional[numpy.ndarray]=None,
        calculate_histogram:Optional[bool]=None,
        histogram_color:str="white",
        preserve_existing_histogram:bool=False
    ):
        """
        display image and histogram of pixel values.
        if image_data is None, then the last displayed image is shown and used for histogram calculation, otherwise the new image overwrites the last one.
        if calculate_histogram is None, the histogram is only calculated when a new image has been provided.
        """

        # if there is a new image, save it, and force histogram calculation
        if not image_data is None:
            self.last_image_data=image_data
            calculate_histogram=True

        def image_type_max_value(_image):
            if _image.dtype==numpy.uint8:
                return 2**8-1
            elif _image.dtype==numpy.uint16:
                return 2**16-1
            else:
                raise Exception(f"{_image.dtype=} unimplemented")

        # calculate histogram
        if calculate_histogram and not self.last_image_data is None:
            image_data=self.last_image_data
            max_value=image_type_max_value(image_data)

            bins=numpy.linspace(0,max_value,129,dtype=image_data.dtype)
            hist,bins=numpy.histogram(image_data,bins=bins)
            hist=hist.astype(numpy.float32)
            if self.histogram_log_scale:
                hist_nonzero_mask=hist!=0
                hist[hist_nonzero_mask]=numpy.log(hist[hist_nonzero_mask])
            hist=hist/hist.max() # normalize to [0;1]

            self.histogramWidget.view.setLimits(
                xMin=0,
                xMax=max_value,
                yMin=0.0,
                yMax=1.0,
                minXRange=bins[4],
                maxXRange=bins[-1],
                minYRange=1.0,
                maxYRange=1.0,
            )
            self.histogramWidget.view.setRange(xRange=(0,max_value))

            plot_kwargs={'x':bins[:-1],'y':hist,'pen':pg.mkPen(color=histogram_color)}
            try:
                if not preserve_existing_histogram:
                    self.histogramWidget.plot_data.clear()
                self.histogramWidget.plot_data.plot(**plot_kwargs)
            except:
                self.histogramWidget.plot_data=self.histogramWidget.addPlot(0,0,title="Histogram",viewBox=self.histogramWidget.view,**plot_kwargs)
                self.histogramWidget.plot_data.hideAxis("left")

        # if there is data to display, apply contrast/brightness settings, then actually display the data
        # also do not actually apply enhancement if brightness and contrast are set to 1.0 (which does not nothing)
        if not self.last_image_data is None:
            image=self.last_image_data

            # since integer conversion truncates or whatever instead of scaling, scale manually
            if image.dtype==numpy.uint16:
                truncated_image=numpy.uint8(image>>8)
            else:
                truncated_image=image
            
            # estimate SNR (signal to noise ratio)
            snr_text="SNR: undefined"
            foreground_mask=image>self.backgroundSlider.value
            if foreground_mask.any() and not foreground_mask.all():
                foreground_mean=truncated_image[foreground_mask].mean()
                background_mean=truncated_image[~foreground_mask].mean()

                if background_mean>0.0:
                    snr_value=foreground_mean/background_mean
                    
                    snr_text=f"SNR: {snr_value:.1f}"

            self.backgroundSNRValueText.setText(snr_text)

            # adjust image brightness and contrast (if required)
            if not (self.imageBrightnessAdjust.value==1.0 and self.imageContrastAdjust.value==1.0):
                image=Image.fromarray(truncated_image) # requires image to be uint8

                if self.imageBrightnessAdjust.value!=1.0:
                    brightness_enhancer = ImageEnhance.Brightness(image)
                    image=brightness_enhancer.enhance(self.imageBrightnessAdjust.value)

                if self.imageContrastAdjust.value!=1.0:
                    contrast_enhancer = ImageEnhance.Contrast(image)
                    image=contrast_enhancer.enhance(self.imageContrastAdjust.value)

                image=numpy.asarray(image) # numpy.array could also be used, but asarray does not copy the image data (read only view)

            # display newly enhanced image
            self.imageDisplayWindow.display_image(image)

        # if there is neither a new nor an old image, only brightness/contrast settings have been changed but there is nothing to display

    def on_well_selection_change(self):
        # clear display
        self.navigationViewer.clear_slide()

        # make sure the current selection is contained in selection buffer, then draw each pov
        self.wellSelectionWidget.itemselectionchanged()
        preview_fov_list=[]
        for well_row,well_column in self.wellSelectionWidget.currently_selected_well_indices:
            x_well,y_well=WELLPLATE_FORMATS[MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT].convert_well_index(well_row,well_column)
            for x_grid_item,y_grid_item in self.multipointController.grid_positions_for_well(x_well,y_well):
                LIGHT_GREY=(160,)*3
                if self.core.fov_exceeds_well_boundary(well_row,well_column,x_grid_item,y_grid_item):
                    grid_item_color=(255,50,140)
                else:
                    grid_item_color=LIGHT_GREY

                self.navigationViewer.draw_fov(x_grid_item,y_grid_item,color=grid_item_color)
                preview_fov_list.append((x_grid_item,y_grid_item))

        self.navigationViewer.preview_fovs=preview_fov_list
        
        # write view to display buffer
        if not self.navigationViewer.last_fov_drawn is None:
            self.navigationViewer.draw_fov(*self.navigationViewer.last_fov_drawn,self.navigationViewer.box_color)

    @TypecheckFunction
    def closeEvent(self, event:QEvent):
        
        self.imageSaver.close()
        self.imageDisplay.close()

        self.core.close()
        
        event.accept()
