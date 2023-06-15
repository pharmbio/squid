from typing import Optional, Callable, List, Union, Any, Tuple
import time, math, os
from enum import Enum
from datetime import datetime
from pathlib import Path
from glob import glob
import traceback

from qtpy.QtCore import Qt, QEvent, Signal
from qtpy.QtWidgets import QMainWindow, QWidget, QSizePolicy, QApplication, QRadioButton, QButtonGroup

from control.camera import Camera
from control._def import MACHINE_CONFIG, TriggerMode, WELLPLATE_NAMES, WellplateFormatPhysical, WELLPLATE_FORMATS, Profiler, AcqusitionProgress, AcquisitionStartResult, AcquisitionImageData, SOFTWARE_NAME, MAIN_LOG, create_current_timestamp
TRIGGER_MODES_LIST=list(TriggerMode)
from control.gui import ObjectManager, HBox, VBox, TabBar, Tab, Button, Dropdown, Label, FileDialog, FILTER_JSON, BlankWidget, Dock, SpinBoxDouble, SpinBoxInteger, Checkbox, Grid, GridItem, flatten, format_seconds_nicely, MessageBox, HasWidget, Window
from control.core import Core, ReferenceFile, CameraWrapper, AcquisitionConfig, ConfigLoadCondition, ConfigLoadConditionSet, DEFAULT_CELL_LINE_STR
from control.core.configuration import Configuration, ConfigurationManager
import control.widgets as widgets
from control.widgets import ComponentLabel
from control.typechecker import TypecheckFunction

from control.web_service import web_service

from threading import Thread, Lock

LAST_PROGRAM_STATE_BACKUP_FILE_PATH="last_program_state.json"

def create_radio_selection(condition_set:ConfigLoadConditionSet,segment:str):
    widget=QWidget()
    button_group=QButtonGroup(parent=widget)
    layout=HBox(with_margins=False).layout
    default_condition=getattr(condition_set,segment)
    for i,arg in enumerate(ConfigLoadCondition):
        new_button=QRadioButton(arg.value,parent=widget)
        new_button.clicked.connect(lambda _,a=arg:setattr(condition_set,segment,a))
        if arg==default_condition:
            new_button.setChecked(True)
        button_group.addButton(new_button,i+1)
        layout.addWidget(new_button)

    widget.setLayout(layout)

    return widget

def create_referenceFile_widget(
    file:str,
    load_callback:Any,
    parent:QWidget,
)->QWidget:
    config=AcquisitionConfig.from_json(file)

    laser_af_reference_is_present:bool=not config.af_laser_reference is None
    condition_set=ConfigLoadConditionSet()

    workaround=dict(
        load_laser_af_data_requested=False,
        condition_set=condition_set, # this is a reference to an object that can be manipulated by the gui below
    )

    def selective_load(file):
        windowworkaround=dict(window=1)
        window=Window(
            VBox(*flatten([
                Label(f"Define for each section of the config file when it should be loaded.\n{ConfigLoadCondition.__doc__}\n"),
                [
                    VBox(
                        Label(" ".join([s[0]+s.lower()[1:] for s in l.split("_")][1:])),
                        create_radio_selection(condition_set,l),

                        with_margins=False
                    )
                    for l
                    in condition_set.__dict__.keys()
                ],
                Button("Load",on_clicked=lambda _,w=workaround,ww=windowworkaround:ww["window"].close() and load_callback(file,w))
            ])).widget,

            title="Load config file sections when..?",
            parent=parent,
        )
        windowworkaround["window"]=window

    return Dock(
        Grid(
            [
                Label(f"Plate type: {config.plate_type}"),
                Label(f"Cell Line: {config.cell_line}"),
            ],
            [
                Checkbox(
                    "Move to Z reference",
                    tooltip="Check this box if you want the objective to move into a position where it can focus on the plate, as indicated by the laser af calibration data contained in the file.",
                    checked=False,
                    enabled=laser_af_reference_is_present,
                    on_stateChanged=lambda s,w=workaround:w.update(dict(
                                                                      load_laser_af_data_requested=s==Qt.CheckState.Checked
                                                                  ))
                ),
                Checkbox("Laser AF data present",tooltip="This box is here just to indicate whether the laser af calibration data is present in the file.",checked=laser_af_reference_is_present,enabled=False),
            ],
            [
                Label(f"Objective: {config.objective}"),
                Label(f"Timestamp: {config.timestamp}"),
            ],
            [
                Button("Load (default)",on_clicked=lambda _,w=workaround:load_callback(file,w)),
                Button("Load (advanced)",on_clicked=lambda _,file=file:selective_load(file)),
            ]
        ).widget,
        title=f"File: {file}",
        minimize_height=True,
    ).widget

class ConfigurationDatabase(QMainWindow):
    def __init__(self,
        parent:QWidget,

        on_load_from_file:Callable[[Optional[str],bool],None],
    ):
        super().__init__(parent=parent)
        self.parent=parent

        self.on_load_from_file=on_load_from_file

        self.custom_file_loader=Label("").widget
        self.custom_file_load_container=HBox(with_margins=False).layout

        self.widget=VBox(
            HBox(
                Label("Load custom file:",tooltip="this will not immediately load the file, it will create a section where you can load this file instead."),
                Button("Browse",on_clicked=lambda _:self.browse_for_custom_load_file()),
            ),
            self.custom_file_load_container,

            Label(""), # empty line
            Label("Load from calibrated reference database :"),
            VBox(*[
                create_referenceFile_widget(reference_file,self.load_file_callback,parent=self.parent)
                for reference_file
                in glob("reference_config_files/*")
            ]),

            Label(""), # empty line
            Label("Load last config :"),
            create_referenceFile_widget(LAST_PROGRAM_STATE_BACKUP_FILE_PATH,self.load_file_callback,parent=self.parent),

            #with_margin=False
        ).widget

        self.setCentralWidget(self.widget)

        self.setWindowTitle("Configuration Database")

    def load_file_callback(self,file,w):
        self.on_load_from_file(file,
                               go_to_z_reference=w["load_laser_af_data_requested"],
                               condition_set=w["condition_set"],
                            )
        self.close()
    
    def browse_for_custom_load_file(self):
        file=FileDialog(mode="open",caption="Load Microscope Acquisition Settings",filter_type=FILTER_JSON).run()
        if file!="":
            BlankWidget(children=[self.custom_file_loader])
            self.custom_file_loader=create_referenceFile_widget(file,self.load_file_callback,parent=self.parent)
            self.custom_file_load_container.addWidget(self.custom_file_loader)
            MAIN_LOG.log(f"loading file {file}")

CAMERA_PIXEL_FORMAT_TOOLTIP="""
Set Camera Pixel Format

Sets the number of bits per pixel, e.g. with Mono8, each pixel is represented by 8 bits and can therefore capture 2^8 possible values (256).

More bits per pixel can capture finer details in the cell morphology, but also take up more storage.
"""
CAMERA_TRIGGER_TOOLTIP="""
Camera trigger type

The trigger type refers to the synchronization between the light source and the camera, i.e. \nhow is 'turn light on' - 'record image' - 'turn light off' coordinated.

Allows setting software / hardware trigger for the main imaging Camera.

Software trigger:
    The computer sends separate signals for light on/off, and camera image recording. May require the light to stay on slightly longer than strictly necessary to record an image.
    e.g. to record an image with 50ms exposure time, the light might only need to stay on for little over 50ms, but with software trigger, due to signal delays etc.
         the light may have to stay on for 70ms in total (exemplary), therefore bleaching the cells more than strictly necessary.

Hardware trigger:
    The computer sends a single signal to the microscope to synchronize the light and image recording using internal hardware logic.
    This may reduce the cell bleaching slightly, compared to software trigger.

    (in practice, we dont see a significant difference in terms of bleaching, but a ~5-10% increase in imaging time, compared to software trigger)
"""

class BasicSettings(QWidget):
    def __init__(self,
        main_camera:Camera,
        
        on_save_all_config:Callable[[],None],
        on_load_all_config:Callable[[],None],
    ):
        super().__init__()

        self.main_camera=main_camera
        self.on_save_all_config=on_save_all_config
        self.on_load_all_config=on_load_all_config

        self.interactive_widgets=ObjectManager()

        DEFAULT_CAMERA_PIXEL_INDEX_INT:int=self.main_camera.pixel_formats.index("Mono12") # list is expected to contain "Mono8" and "Mono12", and Mono12 has been chosen as default

        self.setLayout(VBox(
            HBox(
                Label("Camera Trigger",tooltip=CAMERA_TRIGGER_TOOLTIP),
                self.interactive_widgets.trigger_mode_dropdown == Dropdown(
                    items=TRIGGER_MODES_LIST,
                    tooltip=CAMERA_TRIGGER_TOOLTIP,
                    current_index=TRIGGER_MODES_LIST.index(TriggerMode.SOFTWARE),
                ).widget,
                Label("Camera Pixel Format",tooltip=CAMERA_PIXEL_FORMAT_TOOLTIP),
                self.interactive_widgets.pixel_format == Dropdown(
                    items=self.main_camera.pixel_formats,
                    current_index=DEFAULT_CAMERA_PIXEL_INDEX_INT,
                    tooltip=CAMERA_PIXEL_FORMAT_TOOLTIP,
                    on_currentIndexChanged=self.set_main_camera_pixel_format,
                ).widget,
            ),
            HBox(
                self.interactive_widgets.save_all_config == Button("Save configuration",on_clicked=lambda _btn:self.on_save_all_config()).widget,
                self.interactive_widgets.load_all_config == Button("Load configuration",on_clicked=lambda _btn:self.on_load_all_config()).widget,
            ),
        ).layout)

        self.set_main_camera_pixel_format(DEFAULT_CAMERA_PIXEL_INDEX_INT)

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.interactive_widgets.trigger_mode_dropdown,
            self.interactive_widgets.pixel_format,
            self.interactive_widgets.save_all_config,
            self.interactive_widgets.load_all_config
        ]
    
    @TypecheckFunction
    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        for widget in self.get_all_interactive_widgets():
            if not widget in exceptions:
                widget.setEnabled(set_enabled)

    def set_main_camera_pixel_format(self,pixel_format_index:int):
        new_pixel_format=self.main_camera.pixel_formats[pixel_format_index]
        self.main_camera.camera.set_pixel_format(new_pixel_format)

class Gui(QMainWindow):
    laser_af_validity_changed=Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(SOFTWARE_NAME)
        self.interactive_enabled=True

        # skip_homing is expected to be '1' to skip homing, '0' to not skip it. environment variables are strings though, and bool() cannot parse strings, int() can though. if an env var does not exist, os.environ.get() returns None, so fall back to case where homing is not skipped.
        do_home=not bool(int(os.environ.get('skip_homing') or 0))

        self.core=Core(home=do_home)

        self.basic_settings=BasicSettings(
            main_camera=self.core.main_camera,

            on_save_all_config=self.save_all_config,
            on_load_all_config=self.load_all_config,
        )

        self.imaging_channels_widget=widgets.ImagingChannels(
            configuration_manager=self.core.main_camera.configuration_manager,
            camera_wrapper=self.core.main_camera,

            on_live_status_changed=lambda is_now_live:self.set_all_interactible_enabled(not is_now_live,exceptions=[
                self.imaging_channels_widget.interactive_widgets.live_button,
                self.position_widget.btn_moveZ_forward,
                self.position_widget.btn_moveZ_backward
            ]),
            on_snap_status_changed=lambda is_now_live:self.set_all_interactible_enabled(not is_now_live),
            move_to_offset=lambda offset_um:self.core.laserAutofocusController.move_to_target(target_um=offset_um),
            get_current_position_xy_mm=lambda:(self.core.navigation.x_pos_mm,self.core.navigation.y_pos_mm,self.core.navigation.plate_type)
        )
        self.acquisition_widget=widgets.MultiPointWidget(
            self.core,

            start_experiment=self.start_experiment,
            abort_experiment=self.abort_experiment,

            signal_laser_af_validity_changed=self.laser_af_validity_changed,
        )
        self.well_widget=widgets.WellWidget(
            on_move_to_index=self.core.navigation.move_to_index,
            xy_pos_changed=self.core.navigation.xyPos,
        )
        self.position_widget=widgets.NavigationWidget(
            self.core,
            on_loading_position_toggle=self.loading_position_toggle
        )
        self.autofocus_widget=widgets.AutofocusWidget(
            laser_af_controller = self.core.laserAutofocusController,
            software_af_controller = self.core.autofocusController,
            get_current_z_pos_in_mm = lambda:self.core.navigation.z_pos_mm,

            on_set_all_interactible_enabled=self.set_all_interactible_enabled,

            configuration_manager=self.core.main_camera.configuration_manager,
            laser_af_validity_changed=self.laser_af_validity_changed,
            debug_laser_af=MACHINE_CONFIG.DISPLAY.DEBUG_LASER_AF
        )

        self.setCentralWidget(HBox(
            TabBar(*[
                Tab(title="Live View",widget=self.imaging_channels_widget.live_display.widget),
                Tab(title="Channel View",widget=self.imaging_channels_widget.channel_display),
                *([] if self.autofocus_widget.laser_af_debug_display is None else
                    [Tab(title="Laser AF debug",widget=self.autofocus_widget.laser_af_debug_display)]
                ),
                *([] if self.autofocus_widget.software_af_debug_display is None else
                    [Tab(title="Software AF debug",widget=self.autofocus_widget.software_af_debug_display)]
                ),
            ]),
            VBox(
                self.basic_settings,
                TabBar(
                    Tab(title="Acquisition",widget=VBox(
                        self.acquisition_widget.storage_widget,
                        self.acquisition_widget.grid_widget,
                        self.acquisition_widget.imaging_widget,
                        self.well_widget,
                    ).widget),
                    Tab(title="Lighting and Focus",widget=VBox(
                        self.imaging_channels_widget.snap_channels,
                        self.imaging_channels_widget.channel_config,
                        self.imaging_channels_widget.live_config,
                        Dock(
                            self.position_widget,
                            "Objective/Stage position"
                        ),
                        self.autofocus_widget.af_control,
                    ).widget)
                )
            )
        ).widget)

        # on change of deltax, deltay, wellselection: self.change_acquisition_preview()
        self.acquisition_widget.position_mask_has_changed.connect(lambda:self.change_acquisition_preview())
        self.well_widget.interactive_widgets.well_selection.itemSelectionChanged.connect(lambda:self.change_acquisition_preview())

        host, colon, port = os.environ.get('squid_web_service', '').partition(':')
        if colon:
            @web_service.expose
            def goto_loading():
                self.loading_position_toggle(loading_position_enter=True)

            @web_service.expose
            def leave_loading():
                self.loading_position_toggle(loading_position_enter=False)

            @web_service.expose
            def load_config(
                file_path: str,

                project_override: Optional[str]=None, 
                plate_override: Optional[str]=None
            ):
                self.load_config_from_file(
                    file_path,
                    go_to_z_reference=True,
                    project_override=project_override,
                    plate_override=plate_override,
                    condition_set=ConfigLoadConditionSet.always()
                )

            @web_service.expose
            def acquire():
                if (ok := self.interactive_enabled):
                    web_service.set_status(progress_data={})
                    web_service.set_status(progress_bar_text='')
                    Thread(target=lambda: self.start_experiment()).start()
                return ok

            @web_service.expose
            def list_protocols():
                return sorted(map(str, Path('.').glob('protocols/**/*.json')))

            web_service.start(host, int(port))

    def change_acquisition_preview(self):
        # make sure the current selection is contained in selection buffer, then draw each pov
        self.well_widget.interactive_widgets.well_selection.itemselectionchanged()
        preview_fov_list=[]
        for well_row,well_column in self.well_widget.interactive_widgets.well_selection.currently_selected_well_indices:
            wellplate_format=WELLPLATE_FORMATS[self.well_widget.get_wellplate_type()]
            for x_grid_item,y_grid_item in self.acquisition_widget.get_grid_data().grid_positions_for_well(well_row=well_row,well_column=well_column,plate_type=wellplate_format):
                LIGHT_GREY=(160,)*3
                RED_ISH=(255,50,140)
                if wellplate_format.fov_exceeds_well_boundary(well_row,well_column,x_grid_item,y_grid_item):
                    grid_item_color=RED_ISH
                else:
                    grid_item_color=LIGHT_GREY

                preview_fov_list.append((x_grid_item,y_grid_item,grid_item_color))
        
        # write view to display buffer
        self.well_widget.interactive_widgets.navigation_viewer.set_preview_list(preview_fov_list)

    def loading_position_toggle(self,loading_position_enter:bool):
        """
        callback for when the status of the stage changes with regards to the loading position
        i.e. is called when the stage should enter or leave the loading position
        """
        if loading_position_enter: # entering loading position
            self.set_all_interactible_enabled(set_enabled=False,exceptions=[self.position_widget.btn_goToLoadingPosition]) # disable everything except the single button that can leave the loading position
            self.core.navigation.loading_position_enter()

        else: # leaving loading position
            self.core.navigation.loading_position_leave()
            self.set_all_interactible_enabled(set_enabled=True)

    def start_experiment(self,dry:bool=False)->Union[AcquisitionStartResult,AcquisitionConfig]:

        whole_acquisition_config:AcquisitionConfig=self.get_all_config(dry=dry)

        if dry:
            return AcquisitionStartResult(whole_acquisition_config,"dry")

        # some metadata written to the config file, in addition to the settings directly used for imaging
        additional_data={
            'microscope_name':MACHINE_CONFIG.MACHINE_NAME,
        }

        self.set_all_interactible_enabled(set_enabled=False,exceptions=[self.acquisition_widget.btn_startAcquisition])
        QApplication.processEvents()

        # actually start imaging
        try:
            acquisition_thread=self.core.acquire(
                whole_acquisition_config,
                additional_data=additional_data,

                on_new_acquisition=self.on_step_completed,
                image_return=self.handle_acquired_image,
            )
        
        except Exception as e:
            msg_text:str=str(e)+"\n"*2+"-"*64+"\n"*2+"\n".join(traceback.format_tb(e.__traceback__))
            MAIN_LOG.log(f"an exception occured while starting the experiment: {msg_text}")
            MessageBox("Cannot start acquisition",mode="critical",text=f"An exception occured during acqusition preparation: {msg_text}").run()
            self.set_all_interactible_enabled(set_enabled=True)
            return AcquisitionStartResult(whole_acquisition_config,exception=e)
        
        if acquisition_thread is None:
            return AcquisitionStartResult(whole_acquisition_config,"done")

        return AcquisitionStartResult(whole_acquisition_config,async_signal_on_finish=acquisition_thread.finished)
        
    def handle_acquired_image(self,image_data:AcquisitionImageData):
        self.imaging_channels_widget.live_display.display_image(image_data.image,name=f"{image_data.config.name} in well {image_data.well_name}")
        self.imaging_channels_widget.channel_display.display_image(image_data.image,image_data.config.illumination_source)

        # AcquisitionImageData has fields:
        #   image:numpy.ndarray
        #   path:str
        #   config:Configuration
        #   x:Optional[int]
        #   y:Optional[int]
        #   z:Optional[int]
        #   well_name
    
    def abort_experiment(self):
        MAIN_LOG.log("aborting acquisition on button press")
        self.core.multipointController.request_abort_aquisition()
        # todo kill acquisition thread here if it exists
        
    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return flatten([
            self.basic_settings.get_all_interactive_widgets(),
            self.imaging_channels_widget.get_all_interactive_widgets(),
            self.acquisition_widget.get_all_interactive_widgets(),
            self.well_widget.get_all_interactive_widgets(),
            self.position_widget.get_all_interactive_widgets(),
            self.autofocus_widget.get_all_interactive_widgets(),
        ])

    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        self.basic_settings.set_all_interactible_enabled(set_enabled,exceptions)
        self.imaging_channels_widget.set_all_interactible_enabled(set_enabled,exceptions)
        self.acquisition_widget.set_all_interactible_enabled(set_enabled,exceptions)
        self.well_widget.set_all_interactible_enabled(set_enabled,exceptions)
        self.position_widget.set_all_interactible_enabled(set_enabled,exceptions)
        self.autofocus_widget.set_all_interactible_enabled(set_enabled,exceptions)
        self.interactive_enabled=set_enabled
        web_service.set_status(interactive=set_enabled)

    def on_step_completed(self,progress_data:AcqusitionProgress):
        """
        this function is called every time the acquisition thread considers something to be done
        the first time this function is called (i.e. very few completed steps noted by the acqusition thread), the progress bar is initialized to the full length
        aside, this function will display the progress of the acqusition thread, including an approximation of the imaging time remaining
        """
        web_service.set_status(progress_data=progress_data.__dict__)

        if progress_data.last_completed_action=="acquisition_cancelled":
            time_elapsed_since_start=progress_data.last_step_completion_time-progress_data.start_time
            approx_time_left=time_elapsed_since_start/self.acquisition_progress*(self.total_num_acquisitions-self.acquisition_progress)

            elapsed_time_str=format_seconds_nicely(time_elapsed_since_start)
            progress_bar_text:str=f"cancelled. (acquired {progress_data.completed_steps}/{self.total_num_acquisitions:4} images in {elapsed_time_str})"
            self.acquisition_widget.progress_bar.setFormat(progress_bar_text)
            self.set_all_interactible_enabled(set_enabled=True)
            web_service.set_status(progress_bar_text=progress_bar_text)
            return
        
        if progress_data.completed_steps<=1:
            self.total_num_acquisitions=progress_data.total_steps
            self.acquisition_widget.progress_bar.setValue(0)
            self.acquisition_widget.progress_bar.setMinimum(0)
            self.acquisition_widget.progress_bar.setMaximum(progress_data.total_steps)

            self.well_widget.interactive_widgets.navigation_viewer.redraw_fovs()

            self.completed_steps=0

        if self.completed_steps<progress_data.completed_steps:
            self.completed_steps=progress_data.completed_steps

            self.acquisition_progress=progress_data.completed_steps
            self.acquisition_widget.progress_bar.setValue(self.acquisition_progress)

            time_elapsed_since_start=progress_data.last_step_completion_time-progress_data.start_time
            approx_time_left=time_elapsed_since_start/self.acquisition_progress*(self.total_num_acquisitions-self.acquisition_progress)

            elapsed_time_str=format_seconds_nicely(time_elapsed_since_start)
            if self.acquisition_progress==self.total_num_acquisitions:
                progress_bar_text=f"done. (acquired {self.total_num_acquisitions:4} images in {elapsed_time_str})"
                web_service.set_status(progress_bar_text=progress_bar_text)
                self.acquisition_widget.progress_bar.setFormat(progress_bar_text)
            else:
                approx_time_left_str=format_seconds_nicely(approx_time_left)
                done_percent=int(self.acquisition_progress*100/self.total_num_acquisitions)
                progress_bar_text=f"completed {self.acquisition_progress:4}/{self.total_num_acquisitions:4} images ({done_percent:2}%) in {elapsed_time_str} (eta: {approx_time_left_str})"
                web_service.set_status(progress_bar_text=progress_bar_text)
                self.acquisition_widget.progress_bar.setFormat(progress_bar_text)
            
            if not math.isnan(progress_data.last_imaged_coordinates[0]):
                self.well_widget.interactive_widgets.navigation_viewer.add_history(*progress_data.last_imaged_coordinates)
                QApplication.processEvents()

        if progress_data.last_completed_action=="finished acquisition":
            self.set_all_interactible_enabled(set_enabled=True)

    @TypecheckFunction
    def get_all_config(self,dry:bool=False,allow_invalid_values:bool=False)->AcquisitionConfig:
        if allow_invalid_values and not dry:
            message="non-dry run with invalid values allowed in config can lead to filesystem errors"
            MAIN_LOG.log(f"! error - {message}")
            raise RuntimeError(message)

        # get output paths
        base_dir_str:str=self.acquisition_widget.lineEdit_baseDir.text()
        project_name_str:str=self.acquisition_widget.lineEdit_projectName.text()
        plate_name_str:str=self.acquisition_widget.lineEdit_plateName.text()
        cell_line_str:str=self.acquisition_widget.lineEdit_cellLine.text()

        objective_str:str=MACHINE_CONFIG.MUTABLE_STATE.DEFAULT_OBJECTIVE

        if not allow_invalid_values:
            if len(project_name_str)==0:
                if dry:
                    MessageBox(title="Project name is empty!",mode="critical",text="You did not provide a name for the project. Please provide one.").run()
                raise RuntimeError("project name empty")
            if len(plate_name_str)==0:
                if dry:
                    MessageBox(title="Wellplate name is empty!",mode="critical",text="You did not provide a name for the wellplate. Please provide one.").run()
                raise RuntimeError("wellplate name empty")

        # check validity of output path names
        FORBIDDEN_CHARS={
            " ":"space",
            ",":"comma",
            ":":"colon",
            ";":"semicolon",
            "/":"forward slash",
            "=":"equal sign",
            "&":"ampersand",
            "\\":"backward slash",
            "\t":"tab",
            "\n":"newline",
            "\r":"carriage return",
        }
        if not allow_invalid_values:
            for C,char_name in FORBIDDEN_CHARS.items():
                if C in project_name_str:
                    if dry:
                        MessageBox(title="Forbidden character in Experiment Name!",mode="critical",text=f"Found forbidden character '{C}' ({char_name}) in the Project Name. Please remove the character from the name. (or contact the microscope IT-support: Patrick or Dan)").run()
                    raise RuntimeError("forbidden character in experiment name")

                if C in plate_name_str:
                    if dry:
                        MessageBox(title="Forbidden character in Wellplate Name!",mode="critical",text=f"Found forbidden character '{C}' ({char_name}) in the Wellplate Name. Please remove the character from the name. (or contact the microscope IT-support: Patrick or Dan)").run()
                    raise RuntimeError("forbidden character in wellplate name")

        full_output_path=str(Path(base_dir_str)/project_name_str/plate_name_str)

        # try generating unique experiment ID (that includes current timestamp) until successfull
        def gen_dir_name(base_output_path:str)->Tuple[str,Path]:
            now_str = create_current_timestamp()

            experiment_pathname = base_output_path + '_' + now_str
            return now_str,Path(experiment_pathname)

        timestamp_str,experiment_path=gen_dir_name(base_output_path=full_output_path)
        while experiment_path.exists():
            time.sleep(1) # wait until next second to get a unique experiment ID
            experiment_path=gen_dir_name(base_output_path=full_output_path)
            
        if not (dry or allow_invalid_values):
            experiment_path.mkdir(parents=True) # create a new folder

        return AcquisitionConfig(
            output_path=str(experiment_path),
            project_name=project_name_str,
            plate_name=plate_name_str,
            cell_line=cell_line_str,

            well_list=self.well_widget.get_selected_wells(),

            grid_config=self.acquisition_widget.get_grid_data(),

            af_software_channel=self.acquisition_widget.get_af_software_channel(only_when_enabled=True),
            af_laser_on=self.acquisition_widget.get_af_laser_is_enabled(),
            af_laser_reference=self.autofocus_widget.laser_af_control.get_reference_data(),

            trigger_mode=TRIGGER_MODES_LIST[self.basic_settings.interactive_widgets.trigger_mode_dropdown.currentIndex()],
            pixel_format=self.core.main_camera.pixel_formats[self.basic_settings.interactive_widgets.pixel_format.currentIndex()],
            plate_type=self.well_widget.get_wellplate_type(),

            channels_ordered=self.acquisition_widget.get_selected_channels(),
            channels_config=self.imaging_channels_widget.get_channel_configurations(),

            image_file_format=self.acquisition_widget.get_image_file_format(),
            timestamp=timestamp_str,

            objective=objective_str,
        )

    def save_all_config(self):
        output_file=FileDialog(mode="save",directory=".",caption="Save all configuration data",filter_type=FILTER_JSON).run()
        if len(output_file)==0:
            return
        
        if not output_file.endswith(".json"):
            output_file+=".json"
    
        self.get_all_config(dry=True,allow_invalid_values=True).save_json(file_path=output_file,well_index_to_name=True)

    def load_all_config(self):
        cdb=ConfigurationDatabase(parent=self,on_load_from_file=self.load_config_from_file)
        cdb.show()

    def load_config_from_file(self,
        file_path:Optional[str]=None,

        go_to_z_reference:bool=False,
        condition_set:Optional[ConfigLoadConditionSet]=None,

        project_override: Optional[str]=None, 
        plate_override: Optional[str]=None,
    ):
        """
        if file_path is None, this function will open a dialog to ask for the file to loiad
        """

        # use default set of conditions when none are provided
        if condition_set is None:
            condition_set=ConfigLoadConditionSet()
        
        if file_path is None:
            input_file=FileDialog(mode="open",directory=".",caption="Load all configuration data",filter_type=FILTER_JSON).run()
            if len(input_file)==0:
                return
        else:
            input_file=file_path
        
        config_data=AcquisitionConfig.from_json(file_path=input_file)

        # load the config file segment when the circumstances allow it

        load_project_name=False
        if not project_override is None:
            load_project_name=True
        if condition_set.LOAD_PROJECT_NAME==ConfigLoadCondition.ALWAYS:
            load_project_name=True
        elif condition_set.LOAD_PROJECT_NAME==ConfigLoadCondition.WHEN_EMPTY:
            if self.acquisition_widget.lineEdit_projectName.text()=="":
                load_project_name=True
        if load_project_name:
            self.acquisition_widget.lineEdit_projectName.setText(project_override or config_data.project_name)

        load_plate_name=False
        if not plate_override is None:
            load_plate_name=True
        if condition_set.LOAD_PLATE_NAME==ConfigLoadCondition.ALWAYS:
            load_plate_name=True
        elif condition_set.LOAD_PLATE_NAME==ConfigLoadCondition.WHEN_EMPTY:
            if self.acquisition_widget.lineEdit_plateName.text()=="":
                load_plate_name=True
        if load_plate_name:
            self.acquisition_widget.lineEdit_plateName.setText(plate_override or config_data.plate_name)

        load_cell_line=False
        if condition_set.LOAD_CELL_LINE==ConfigLoadCondition.ALWAYS:
            load_cell_line=True
        elif condition_set.LOAD_CELL_LINE==ConfigLoadCondition.WHEN_EMPTY:
            current_cell_line=self.acquisition_widget.lineEdit_cellLine.text()
            if current_cell_line in ("",DEFAULT_CELL_LINE_STR):
                load_cell_line=True
        if load_cell_line:
            self.acquisition_widget.lineEdit_cellLine.setText(config_data.cell_line)

        # there is always a trigger mode set, so only load when overwriting is allowed
        if condition_set.LOAD_TRIGGER_MODE==ConfigLoadCondition.ALWAYS:
            self.basic_settings.interactive_widgets.trigger_mode_dropdown.setCurrentIndex(TRIGGER_MODES_LIST.index(config_data.trigger_mode))

        # there is always a pixel format set, so only load when overwriting is allowed
        if condition_set.LOAD_PIXEL_FORMAT==ConfigLoadCondition.ALWAYS:
            self.basic_settings.interactive_widgets.pixel_format.setCurrentIndex(self.core.main_camera.pixel_formats.index(config_data.pixel_format))
        
        # there is always an image file format set, so only load when overwriting is allowed
        if condition_set.LOAD_IMAGE_FILE_FORMAT==ConfigLoadCondition.ALWAYS:
            self.acquisition_widget.set_image_file_format(config_data.image_file_format)

        # there are always grid settings present, so only load when overwriting is allowed
        if condition_set.LOAD_GRID_CONFIG==ConfigLoadCondition.ALWAYS:
            self.acquisition_widget.set_grid_data(config_data.grid_config)

        # there is always a plate type set, so only load when overwriting is allowed
        if condition_set.LOAD_PLATE_TYPE==ConfigLoadCondition.ALWAYS:
            self.well_widget.change_wellplate_type_by_type(config_data.plate_type)

        # there is always an objective set, so only load when overwriting is allowed
        if condition_set.LOAD_OBJECTIVE==ConfigLoadCondition.ALWAYS:
            self.well_widget.set_objective(config_data.objective,ignore_invalid=True)

        load_well_selection=False
        if condition_set.LOAD_WELL_SELECTION==ConfigLoadCondition.ALWAYS:
            load_well_selection=True
        elif condition_set.LOAD_WELL_SELECTION==ConfigLoadCondition.WHEN_EMPTY:
            if len(self.well_widget.get_selected_wells())==0:
                load_well_selection=True
        if load_well_selection:
            self.well_widget.set_selected_wells(config_data.well_list) # set selected wells after change of wellplate type (changing wellplate type may clear or invalidate parts of the current well selection)
        
        load_channel_selection=False
        if condition_set.LOAD_CHANNEL_SELECTION==ConfigLoadCondition.ALWAYS:
            load_channel_selection=True
        elif condition_set.LOAD_CHANNEL_SELECTION==ConfigLoadCondition.WHEN_EMPTY:
            if len(self.acquisition_widget.get_selected_channels())==0:
                load_channel_selection=True
        if load_channel_selection:
            self.acquisition_widget.set_selected_channels(config_data.channels_ordered)

        # there is always channel configuration data present, so only load when overwriting is allowed
        if condition_set.LOAD_CHANNEL_CONFIG==ConfigLoadCondition.ALWAYS:
            self.imaging_channels_widget.set_channel_configurations(config_data.channels_config)

        load_laser_af_reference=False
        load_laser_af_enabled=False
        if not config_data.af_laser_reference is None:
            if condition_set.LOAD_CHANNEL_SELECTION==ConfigLoadCondition.ALWAYS:
                load_laser_af_reference=True
            elif condition_set.LOAD_CHANNEL_SELECTION==ConfigLoadCondition.WHEN_EMPTY:
                if not self.autofocus_widget.laser_af_control.laserAutofocusController.is_initialized:
                    load_laser_af_reference=True
            if load_laser_af_reference:
                self.autofocus_widget.laser_af_control.set_reference_data(config_data.af_laser_reference)

            if condition_set.LOAD_AF_LASER_ON==ConfigLoadCondition.ALWAYS:
                load_laser_af_enabled=True
            elif condition_set.LOAD_AF_LASER_ON==ConfigLoadCondition.WHEN_EMPTY:
                if not self.acquisition_widget.get_af_laser_is_enabled():
                    load_laser_af_enabled=True
            if load_laser_af_enabled:
                self.acquisition_widget.set_af_laser_is_enabled(config_data.af_laser_on)

        if go_to_z_reference:
            if config_data.af_laser_reference is None:
                MAIN_LOG.log("warning - you specified to move to reference z but there is no laser af data present")
            else:
                if not load_laser_af_reference:
                    MAIN_LOG.log("warning - you specified to move to reference z without loading the laser af data")

                z_mm=config_data.af_laser_reference.z_um_at_reference*1e-3
                MAIN_LOG.log(f"focus - moving objective to {z_mm=:.3f}")
                
                self.core.navigation.move_z_to(z_mm=z_mm,wait_for_completion={})

    def closeEvent(self, event:QEvent):

        self.get_all_config(dry=True,allow_invalid_values=True).save_json(file_path=LAST_PROGRAM_STATE_BACKUP_FILE_PATH,well_index_to_name=True)

        self.core.close()
        
        event.accept()

