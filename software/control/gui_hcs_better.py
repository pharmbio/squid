from typing import Optional, Callable, List, Union, Any
import time
from datetime import datetime
from pathlib import Path
import math

from qtpy.QtCore import Qt, QEvent, Signal
from qtpy.QtWidgets import QMainWindow, QWidget, QSizePolicy, QApplication

from control.camera import Camera
from control._def import MACHINE_CONFIG, TriggerMode, WELLPLATE_NAMES, WellplateFormatPhysical, WELLPLATE_FORMATS, Profiler, AcqusitionProgress, AcquisitionStartResult, AcquisitionImageData
TRIGGER_MODES_LIST=list(TriggerMode)
from control.gui import ObjectManager, HBox, VBox, TabBar, Tab, Button, Dropdown, Label, FileDialog, FILTER_JSON, BlankWidget, Dock, SpinBoxDouble, SpinBoxInteger, Checkbox, Grid, GridItem, flatten, format_seconds_nicely, MessageBox, HasWidget
from control.core import Core, ReferenceFile, CameraWrapper, AcquisitionConfig
from control.core.configuration import Configuration, ConfigurationManager
import control.widgets as widgets
from control.widgets import ComponentLabel
from control.typechecker import TypecheckFunction

LAST_PROGRAM_STATE_BACKUP_FILE_PATH="last_program_state.json"

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

        self.setLayout(VBox(
            HBox(
                Label("Camera Trigger",tooltip="Camera trigger type. If you don't know this does, chances are you don't need to change it. (Hardware trigger may reduce bleaching effect slightly)"),
                self.interactive_widgets.trigger_mode_dropdown == Dropdown(
                    items=TRIGGER_MODES_LIST,
                    current_index=TRIGGER_MODES_LIST.index(TriggerMode.SOFTWARE),
                ).widget,
                Label("Camera Pixel Format",tooltip="Change camera pixel format. Larger number of bits per pixel can provide finer granularity (no impact on value range) of the recorded signal, but also takes up more storage."),
                self.interactive_widgets.pixel_format == Dropdown(
                    items=self.main_camera.pixel_formats,
                    current_index=self.main_camera.pixel_formats.index("Mono12"), # list contains "Mono8" and "Mono12"
                    on_currentIndexChanged=self.set_main_camera_pixel_format,
                ).widget,
            ),
            HBox(
                self.interactive_widgets.save_all_config == Button("Save configuration",on_clicked=self.save_all_config).widget,
                self.interactive_widgets.load_all_config == Button("Load configuration",on_clicked=self.open_config_load_popup).widget,
            ),
        ).layout)

        self.set_main_camera_pixel_format(0) # default pixel format has been decided to be 8 bits

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.interactive_widgets.trigger_mode_dropdown,
            self.interactive_widgets.pixel_format,
            self.interactive_widgets.save_all_config,
            self.interactive_widgets.load_all_config
        ]
    
    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        for widget in self.get_all_interactive_widgets():
            if not widget in exceptions:
                widget.setEnabled(set_enabled)

    def set_main_camera_pixel_format(self,pixel_format_index:int):
        new_pixel_format=self.main_camera.pixel_formats[pixel_format_index]
        self.main_camera.camera.set_pixel_format(new_pixel_format)

    def save_all_config(self):
        self.on_save_all_config()

    def load_all_config(self):
        self.on_load_all_config()

    def open_config_load_popup(self):
        self.on_load_all_config()

        # open window instead to load config from database (calibrated laser AF and approximate focus z position based on combination wellplate type + cell line)
        # also has interface to load only parts of a config file, e.g. checkboxes to select loading of certain parts of the whole-program config

        print("stub def open_config_load_popup(self):")

class Gui(QMainWindow):
    laser_af_validity_changed=Signal(bool)

    def __init__(self):
        super().__init__()

        self.core=Core(home=True)

        self.basic_settings=BasicSettings(
            main_camera=self.core.main_camera,

            on_save_all_config=self.save_all_config,
            on_load_all_config=self.load_all_config,
        )

        self.imaging_channels_widget=widgets.ImagingChannels(
            configuration_manager=self.core.main_camera.configuration_manager,
            camera_wrapper=self.core.main_camera,

            on_live_status_changed=lambda is_now_live:self.set_all_interactible_enabled(not is_now_live,exceptions=[self.imaging_channels_widget.interactive_widgets.live_button]),
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

            on_set_all_callbacks_enabled=self.set_all_interactible_enabled,

            configuration_manager=self.core.main_camera.configuration_manager,
            laser_af_validity_changed=self.laser_af_validity_changed,
        )

        self.setCentralWidget(HBox(
            TabBar(*[
                Tab(title="Live View",widget=self.imaging_channels_widget.live_display.widget),
                Tab(title="Channel View",widget=self.imaging_channels_widget.channel_display.widget),
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
        self.acquisition_widget.entry_deltaX.valueChanged.connect(lambda:self.change_acquisition_preview())
        self.acquisition_widget.entry_deltaY.valueChanged.connect(lambda:self.change_acquisition_preview())
        self.acquisition_widget.entry_NX.valueChanged.connect(lambda:self.change_acquisition_preview())
        self.acquisition_widget.entry_NY.valueChanged.connect(lambda:self.change_acquisition_preview())
        self.well_widget.interactive_widgets.well_selection.itemSelectionChanged.connect(lambda:self.change_acquisition_preview())

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
            return whole_acquisition_config

        # some metadata written to the config file, in addition to the settings directly used for imaging
        additional_data={
            'project_name':whole_acquisition_config.project_name,
            'plate_name':whole_acquisition_config.plate_name,
            'timestamp':datetime.now().replace(microsecond=0).isoformat(sep='_'),
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
            MessageBox("Cannot start acquisition",mode="critical",text=f"An exception occured during acqusition preparation: {str(e)}").run()
            self.set_all_interactible_enabled(set_enabled=True)
            return AcquisitionStartResult(exception=e)
        
        if acquisition_thread is None:
            return AcquisitionStartResult("done")

        return AcquisitionStartResult(async_signal_on_finish=acquisition_thread.finished)
        
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
        print("aborting acquisition on button press")
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

    def on_step_completed(self,progress_data:AcqusitionProgress):
        """
        this function is called every time the acquisition thread considers something to be done
        the first time this function is called (i.e. very few completed steps noted by the acqusition thread), the progress bar is initialized to the full length
        aside, this function will display the progress of the acqusition thread, including an approximation of the imaging time remaining
        """
        if progress_data.last_completed_action=="acquisition_cancelled":
            time_elapsed_since_start=progress_data.last_step_completion_time-progress_data.start_time
            approx_time_left=time_elapsed_since_start/self.acquisition_progress*(self.total_num_acquisitions-self.acquisition_progress)

            elapsed_time_str=format_seconds_nicely(time_elapsed_since_start)
            self.acquisition_widget.progress_bar.setFormat(f"cancelled. (acquired {progress_data.completed_steps}/{self.total_num_acquisitions:4} images in {elapsed_time_str})")
            self.set_all_interactible_enabled(set_enabled=True)
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
                self.acquisition_widget.progress_bar.setFormat(f"done. (acquired {self.total_num_acquisitions:4} images in {elapsed_time_str})")
            else:
                approx_time_left_str=format_seconds_nicely(approx_time_left)
                done_percent=int(self.acquisition_progress*100/self.total_num_acquisitions)
                progress_bar_text=f"completed {self.acquisition_progress:4}/{self.total_num_acquisitions:4} images ({done_percent:2}%) in {elapsed_time_str} (eta: {approx_time_left_str})"
                self.acquisition_widget.progress_bar.setFormat(progress_bar_text)
            
            if not math.isnan(progress_data.last_imaged_coordinates[0]):
                self.well_widget.interactive_widgets.navigation_viewer.add_history(*progress_data.last_imaged_coordinates)
                QApplication.processEvents()

        if progress_data.last_completed_action=="finished acquisition":
            self.set_all_interactible_enabled(set_enabled=True)

    def get_all_config(self,dry:bool=False,allow_invalid_values:bool=False)->AcquisitionConfig:
        # get output paths
        base_dir_str=self.acquisition_widget.lineEdit_baseDir.text()
        project_name_str=self.acquisition_widget.lineEdit_projectName.text()
        plate_name_str=self.acquisition_widget.lineEdit_plateName.text()

        if len(project_name_str)==0 and not allow_invalid_values:
            if dry:
                MessageBox(title="Project name is empty!",mode="critical",text="You did not provide a name for the project. Please provide one.").run()
            raise RuntimeError("project name empty")
        if len(plate_name_str)==0 and not allow_invalid_values:
            if dry:
                MessageBox(title="Wellplate name is empty!",mode="critical",text="You did not provide a name for the wellplate. Please provide one.").run()
            raise RuntimeError("wellplate name empty")

        # check validity of output path names
        FORBIDDEN_CHARS={
            " ":"space",
            ",":"comma",
            ":":"colon",
            "/":"forward slash",
            "\\":"backward slash",
            "\t":"tab",
            "\n":"newline? (enter key)",
            "\r":"carriage return?! contact support (patrick/dan)!",
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

        return AcquisitionConfig(
            output_path=full_output_path,
            project_name=project_name_str,
            plate_name=plate_name_str,
            well_list=self.well_widget.get_selected_wells(),
            grid_mask=self.acquisition_widget.get_grid_mask(),
            grid_config=self.acquisition_widget.get_grid_data(),
            #af_software_channel:Optional[str]=None,
            af_laser_on=self.acquisition_widget.interactive_widgets.checkbox_laserAutofocus.checkState()==Qt.Checked,
            #af_laser_reference:Optional[LaserAutofocusData]=None,
            trigger_mode=TRIGGER_MODES_LIST[self.basic_settings.interactive_widgets.trigger_mode_dropdown.currentIndex()],
            pixel_format=self.core.main_camera.pixel_formats[self.basic_settings.interactive_widgets.pixel_format.currentIndex()],
            plate_type=self.well_widget.get_wellplate_type(),
            channels_ordered=self.acquisition_widget.get_selected_channels(),
            channels_config=self.imaging_channels_widget.get_channel_configurations(),
            image_file_format=self.acquisition_widget.get_image_file_format(),
        )

    def save_all_config(self):
        output_file=FileDialog(mode="save",directory=".",caption="Save all configuration data",filter_type=FILTER_JSON).run()
        if len(output_file)==0:
            return
        
        if not output_file.endswith(".json"):
            output_file+=".json"
    
        self.get_all_config(dry=True,allow_invalid_values=True).save_json(file_path=output_file,well_index_to_name=True)

    def load_all_config(self):
        input_file=FileDialog(mode="open",directory=".",caption="Load all configuration data",filter_type=FILTER_JSON).run()
        if len(input_file)==0:
            return
        
        config_data=AcquisitionConfig.from_json(file_path=input_file)
        
        #self.acquisition_widget.lineEdit_baseDir.setText()
        self.acquisition_widget.lineEdit_projectName.setText(config_data.project_name)
        self.acquisition_widget.lineEdit_plateName.setText(config_data.plate_name)

        self.basic_settings.interactive_widgets.trigger_mode_dropdown.setCurrentIndex(TRIGGER_MODES_LIST.index(config_data.trigger_mode))
        self.basic_settings.interactive_widgets.pixel_format.setCurrentIndex(self.core.main_camera.pixel_formats.index(config_data.pixel_format))
        self.acquisition_widget.set_image_file_format(config_data.image_file_format)

        self.acquisition_widget.set_grid_data(config_data.grid_config)
        self.acquisition_widget.set_grid_mask(config_data.grid_mask) # set mask after grid settings! (setting grid settings overwrites mask state)
        self.well_widget.change_wellplate_type_by_type(config_data.plate_type)
        self.well_widget.set_selected_wells(config_data.well_list) # set selected wells after change of wellplate type (changing wellplate type may clear or invalidate parts of the current well selection)
        self.acquisition_widget.set_selected_channels(config_data.channels_ordered)
        self.imaging_channels_widget.set_channel_configurations(config_data.channels_config)

    def closeEvent(self, event:QEvent):

        self.get_all_config(dry=False,allow_invalid_values=True).save_json(file_path=LAST_PROGRAM_STATE_BACKUP_FILE_PATH,well_index_to_name=True)

        self.core.close()
        
        event.accept()

