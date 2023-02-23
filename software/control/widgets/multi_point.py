# qt libraries
from qtpy.QtCore import Qt, QModelIndex, QSize, Signal, QEvent, QObject
from qtpy.QtWidgets import QFrame, QPushButton, QLineEdit, \
    QLabel, QAbstractItemView, QProgressBar, QDesktopWidget, \
    QWidget, QSizePolicy, QApplication, QComboBox, QAbstractScrollArea
from qtpy.QtGui import QIcon, QMouseEvent

from control._def import AcquisitionStartResult, MACHINE_CONFIG, ImageFormat, Acquisition

from typing import Optional, Union, List, Tuple, Callable

from control.core import Core, MultiPointController, ConfigurationManager, GridDimensionConfig, WellGridConfig, AcquisitionConfig, LaserAutofocusData, DEFAULT_CELL_LINE_STR
from control.typechecker import TypecheckFunction
from control.gui import *

from enum import Enum
import subprocess, os
from datetime import datetime

import numpy

class ComponentLabels(str,Enum):
    BUTTON_START_ACQUISITION_IDLE_TEXT="Start Acquisition"
    BUTTON_START_ACQUISITION_RUNNING_TEXT="Cancel Acquisition"

    IMAGE_FORMAT_TOOLTIP="change file format for images acquired with the multi point acquisition function"
    COMPRESSION_TOOLTIP="Enable (lossless) image file compression (only supported by TIF)"
    SOFTWARE_AUTOFOCUS_TOOLTIP="""
    Enable software autofocus for multipoint acquisition

    Once per well (?), software autofocus will be performed, i.e. a z-stack is imaged, a focus measure calculated for each image in the stack, then the objective will move to the z-position at which the most in-focus picture was taken.
    Note that the focus once per well may not be enough for certain well plate types to have in-focus images outside of the image taken at the position where the autofocus procedure was performed.

    Note: Use laser or software autofocus exclusively! (or neither)
    """
    AF_CHANNEL_TOOLTIP="Set imaging channel that will be used to calculate a focus measure for the z-stack. See software autofocus checkbox tooltip for details."
    LASER_AUTOFOCUS_TOOLTIP="""
    Enable laser autofocus for multipoint acquisition.

    For each imaged position the offset from a reference plane will be measured, then the objective moved so that it is in the focus plane for the current position.

    For each of the 5 channels there can be a channel-specific offset from the reference plane to account for differences in (average) organelle height over the bottom of the well plate.
    This value can be positive or negative, so you are free to choose any channel as reference.

    A channel specific offset other than zero will increase the overall imaging time.
    Offset values below 0.3 will be considered zero.

    If this checkbox is disabled (i.e. cannot be clicked/checked), the laser autofocus has not been properly initialized (needs to be done manually before starting multi-point acquisition).

    To initialize the laser autofocus:
    1. Bring the reference channel in any well into focus.
    2. In the 'Laser Autofocus' panel below, press the 'Initialize' Button. (see this buttons tooltip for more info)
    3. Click 'Set as reference plane'. (see this buttons tooltip for more info)
    4. Click 'Measure Displacement'. The number should be close to zero if the objective (and stage) has not been moved after the last reference plane was set.

    Note: Use laser or software autofocus exclusively! (or neither)
    """

    dx_tooltip="""
    acquire grid of images (Nx images with dx mm in between acquisitions; dx does not matter if Nx is 1)
    can be combined with dy/Ny and dz/Nz and dt/Nt for a total of Nx * Ny * Nz * Nt images
    """
    dy_tooltip="""
    acquire grid of images (Ny images with dy mm in between acquisitions; dy does not matter if Ny is 1)
    can be combined with dx/Nx and dz/Nz and dt/Nt for a total of Nx*Ny*Nz*Nt images
    """
    dz_tooltip="""
    acquire z-stack of images (Nz images with dz µm in between acquisitions; dz does not matter if Nz is 1)
    can be combined with dx/Nx and dy/Ny and dt/Nt for a total of Nx*Ny*Nz*Nt images
    """
    dt_tooltip="""
    acquire time-series of 'Nt' images, with 'dt' seconds in between acquisitions (dt does not matter if Nt is 1)
    can be combined with dx/Nx and dy/Ny and dz/Nz for a total of Nx*Ny*Nz*Nt images
    """

UNSELECTED_GRID_POSITION_COLOR="lightgrey"
SELECTED_GRID_POSITION_COLOR="lightblue"

delta_x_min=0.1
delta_x_max=5.0
delta_x_step=0.1
delta_y_min=0.1
delta_y_max=5.0
delta_y_step=0.1
delta_z_min=0.1
delta_z_max=None
delta_z_step=0.2
delta_t_min=1.0
delta_t_max=None
delta_t_step=0.1
NX_min=1
NX_max=10
NY_min=1
NY_max=10
NZ_min=1
NZ_max=10
Nt_min=1
Nt_max=10

class MultiPointWidget(QObject):
    @property
    def multipointController(self)->MultiPointController:
        return self.core.multipointController
    
    core:Core

    start_experiment:Callable[[],Union[AcquisitionStartResult,AcquisitionConfig]]
    abort_experiment:Callable[[],None]

    signal_laser_af_validity_changed:Signal # signal[bool]

    base_path_is_set:bool

    storage_widget:QWidget
    grid_widget:QWidget
    imaging_widget:QWidget

    position_mask_has_changed:Signal=Signal()

    def __init__(self,
        core:Core,

        start_experiment:Callable[[Any],None],
        abort_experiment:Callable[[],None],

        signal_laser_af_validity_changed:Signal,
    ):
        """ start_experiment callable may return signal that is emitted on experiment completion"""

        super().__init__()
        
        self.core = core
        self.start_experiment=start_experiment
        self.abort_experiment=abort_experiment
        self.is_laser_af_initialized=False
        signal_laser_af_validity_changed.connect(self.on_laser_af_validity_changed)

        self.base_path_is_set = False

        self.interactive_widgets=ObjectManager()

        # add image saving options (path where to save)
        self.btn_setBaseDir = Button('Browse',default=False,on_clicked=self.set_saving_dir).widget
        self.btn_setBaseDir.setIcon(QIcon('icon/folder.png'))
        
        self.lineEdit_baseDir = QLineEdit()
        self.lineEdit_baseDir.setReadOnly(True)
        self.lineEdit_baseDir.setText(MACHINE_CONFIG.DISPLAY.DEFAULT_SAVING_PATH)
        self.base_path_is_set = True

        self.lineEdit_projectName = QLineEdit()
        self.lineEdit_plateName = QLineEdit()
        self.lineEdit_cellLine = QLineEdit()
        self.lineEdit_cellLine.setText(DEFAULT_CELL_LINE_STR)

        self.image_format_widget=Dropdown(
            items=["BMP","TIF","TIF (compr.)"],
            current_index=list(ImageFormat).index(Acquisition.IMAGE_FORMAT),
            tooltip=ComponentLabels.IMAGE_FORMAT_TOOLTIP,
        ).widget

        self.storage_widget=Grid(
            [
                QLabel('Base Path:'),
                GridItem(self.lineEdit_baseDir,colSpan=2),
                self.btn_setBaseDir,
            ],
            [
                QLabel('Project Name:'),
                self.lineEdit_projectName,
                GridItem(Label("Image Format:",tooltip="File format used for the saved images.\nTIF is a widely supported format, but might take up a lot of space.\nTIF (comp.) compresses images (lossless) before saving as TIF files, which can reduce the filesize, but may not be as widely compatible with other software.\nBMP should only be used under special circumstances.").widget,row=1),
                self.image_format_widget,
            ],
            [
                QLabel('Plate Name:'),
                GridItem(self.lineEdit_plateName,colSpan=3),
            ],
            [
                QLabel('Cell line:'),
                GridItem(self.lineEdit_cellLine,colSpan=3),
            ],

            with_margins=False,
        ).widget

        # add imaging grid configuration options
        self.entry_deltaX = SpinBoxDouble(
            minimum=delta_x_min,
            maximum=delta_x_max,
            step=delta_x_step,
            default=self.multipointController.deltaX,
            num_decimals=3,
            keyboard_tracking=False,
            enabled=self.multipointController.NX > 1
        ).widget

        self.entry_NX = SpinBoxInteger(minimum=NX_min,maximum=NX_max,default=self.multipointController.NX,keyboard_tracking=False,on_valueChanged=[
            lambda new_value:self.entry_deltaX.setDisabled(new_value==1),
            lambda _btn:self.grid_changed(True)
        ]).widget

        self.entry_deltaY = SpinBoxDouble(
            minimum=delta_y_min,
            maximum=delta_y_max,
            step=delta_y_step,
            default=self.multipointController.deltaY,
            num_decimals=3,
            keyboard_tracking=False,
            enabled=self.multipointController.NY > 1
        ).widget
        
        self.entry_NY = SpinBoxInteger(minimum=NY_min,maximum=NY_max,default=self.multipointController.NY,keyboard_tracking=False,on_valueChanged=[
            lambda new_value:self.entry_deltaY.setDisabled(new_value==1),
            lambda _btn:self.grid_changed(True)
        ]).widget

        self.entry_deltaZ = SpinBoxDouble(
            minimum=delta_z_min,
            maximum=delta_z_max,
            step=delta_y_step,
            default=self.multipointController.deltaZ,
            num_decimals=3,
            keyboard_tracking=False,
            enabled=self.multipointController.NZ > 1
        ).widget
        
        self.entry_NZ = SpinBoxInteger(minimum=NZ_min,maximum=NZ_max,default=self.multipointController.NZ,keyboard_tracking=False,on_valueChanged=[
            lambda new_value:self.entry_deltaZ.setDisabled(new_value==1),
        ]).widget
        
        self.entry_dt = SpinBoxDouble(
            minimum=delta_t_min,
            maximum=delta_t_max,
            step=delta_t_step,
            default=self.multipointController.deltat,
            num_decimals=3,
            keyboard_tracking=False,
            enabled=self.multipointController.Nt > 1
        ).widget

        self.entry_Nt = SpinBoxInteger(minimum=Nt_min,maximum=Nt_max,default=self.multipointController.Nt,keyboard_tracking=False,on_valueChanged=[
            lambda new_value:self.entry_dt.setDisabled(new_value==1),
        ]).widget

        self.well_grid_selector=None
        self.grid_changed(True)
        assert not self.well_grid_selector is None

        self.grid_widget=Dock(
            Grid(
                [ Label('num acq. in x',tooltip=ComponentLabels.dx_tooltip), self.entry_NX, Label('delta x (mm)',tooltip=ComponentLabels.dx_tooltip), self.entry_deltaX,],
                [ Label('num acq. in y',tooltip=ComponentLabels.dy_tooltip), self.entry_NY, Label('delta y (mm)',tooltip=ComponentLabels.dy_tooltip), self.entry_deltaY,],
                [ Label('num acq. in z',tooltip=ComponentLabels.dz_tooltip), self.entry_NZ, Label('delta z (um)',tooltip=ComponentLabels.dz_tooltip), self.entry_deltaZ,],
                [ Label('num acq. in t',tooltip=ComponentLabels.dt_tooltip), self.entry_Nt, Label('delta t (s)', tooltip=ComponentLabels.dt_tooltip), self.entry_dt, ],

                GridItem(self.well_grid_selector,0,4,4,1)
            ).widget,
            "Grid imaging settings"
        ).widget

        # add channel selection (and order specification)
        self.list_channel_names=[mc.name for mc in self.core.main_camera.configuration_manager.configurations]
        self.list_configurations = ItemList(
            items=self.list_channel_names,
        ).widget
        self.list_configurations.setSelectionMode(QAbstractItemView.MultiSelection) # ref: https://doc.qt.io/qt-5/qabstractitemview.html#SelectionMode-enum
        self.list_configurations.setDragDropMode(QAbstractItemView.InternalMove) # allow moving items within list
        self.list_configurations.model().rowsMoved.connect(self.channel_list_rows_moved)
        num_items_in_list=len(self.list_channel_names)
        item_height=18 # TODO get real value, not just guess a good looking one..
        self.list_configurations.setMinimumHeight(num_items_in_list*item_height)

        # add software AF (currently disabled, because laser AF is just so much better, and we have not found a case where it does not work)
        self.checkbox_withAutofocus = Checkbox(
            label="Software AF",
            checked=False,#MACHINE_CONFIG.DISPLAY.MULTIPOINT_SOFTWARE_AUTOFOCUS_ENABLE_BY_DEFAULT,
            tooltip=ComponentLabels.SOFTWARE_AUTOFOCUS_TOOLTIP,
            on_stateChanged=lambda new_state:self.af_channel_dropdown.setEnabled(new_state==Qt.Checked)
        ).widget

        self.af_software_channel_names=[microscope_configuration.name for microscope_configuration in self.core.main_camera.configuration_manager.configurations]
        self.af_channel_dropdown=Dropdown(
            items=self.af_software_channel_names,
            current_index=self.af_software_channel_names.index(self.multipointController.autofocus_channel_name),
            tooltip=ComponentLabels.AF_CHANNEL_TOOLTIP,
            enabled=MACHINE_CONFIG.DISPLAY.MULTIPOINT_SOFTWARE_AUTOFOCUS_ENABLE_BY_DEFAULT,
            on_currentIndexChanged=lambda index:setattr(MACHINE_CONFIG.MUTABLE_STATE,"MULTIPOINT_AUTOFOCUS_CHANNEL",self.af_software_channel_names[index])
        ).widget

        # add laser AF
        self.interactive_widgets.checkbox_laserAutofocus = Checkbox(
            label="Laser AF",
            checked=False,
            enabled=False,
            tooltip=ComponentLabels.LASER_AUTOFOCUS_TOOLTIP,
        ).widget

        self.btn_startAcquisition = Button(ComponentLabels.BUTTON_START_ACQUISITION_IDLE_TEXT,on_clicked=self.toggle_acquisition).widget

        grid_multipoint_acquisition_config=Grid(
            #[self.checkbox_withAutofocus], # see software AF comment above
            #[self.af_channel_dropdown],
            [self.interactive_widgets.checkbox_laserAutofocus],
            [self.btn_startAcquisition],

            with_margins=False,
        ).widget

        self.progress_bar=QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1)
        self.progress_bar.setValue(0)

        self.imaging_widget=Grid(
            GridItem( self.list_configurations,           row=0, column=0, colSpan=2 ),
            GridItem( grid_multipoint_acquisition_config, row=0, column=2, colSpan=2 ),
            GridItem( self.progress_bar,                  row=1, column=0, colSpan=4 ),
            
            with_margins=False,
        ).widget

        self.acquisition_is_running=False

    @TypecheckFunction
    def on_laser_af_validity_changed(self,new_validity:bool):
        """
        callback for a signal that says whether the laser af is now valid or not
        """
        self.is_laser_af_initialized=new_validity
        self.interactive_widgets.checkbox_laserAutofocus.setEnabled(new_validity)
        self.interactive_widgets.checkbox_laserAutofocus.setCheckState(Qt.Unchecked) # uncheck it when validity change to invalid, but also uncheck otherwise because why not

    @TypecheckFunction
    def set_grid_data(self,new_grid_data:WellGridConfig):
        assert new_grid_data.x.unit=="mm"
        self.entry_deltaX.setValue(new_grid_data.x.d)
        self.entry_NX.setValue(new_grid_data.x.N)
        assert new_grid_data.y.unit=="mm"
        self.entry_deltaY.setValue(new_grid_data.y.d)
        self.entry_NY.setValue(new_grid_data.y.N)
        assert new_grid_data.z.unit=="mm"
        self.entry_deltaZ.setValue(new_grid_data.z.d*1000)
        self.entry_NZ.setValue(new_grid_data.z.N)
        assert new_grid_data.t.unit=="s"
        self.entry_dt.setValue(new_grid_data.t.d)
        self.entry_Nt.setValue(new_grid_data.t.N)

        for row_i,row in enumerate(new_grid_data.mask):
            for column_i,element in enumerate(row):
                self.toggle_well_grid_selection(_event_data=None,row=row_i,column=column_i,override_selected_state=bool(element))

        # manually call callback to refresh acquisition preview in navigation viewer widget
        self.grid_changed(True)

    @TypecheckFunction
    def get_grid_data(self)->WellGridConfig:
        return WellGridConfig(
            x=GridDimensionConfig(
                d=self.entry_deltaX.value(),
                N=self.entry_NX.value(),
                unit="mm",
            ),
            y=GridDimensionConfig(
                d=self.entry_deltaY.value(),
                N=self.entry_NY.value(),
                unit="mm",
            ),
            z=GridDimensionConfig(
                d=self.entry_deltaZ.value()/1000.0,
                N=self.entry_NZ.value(),
                unit="mm",
            ),
            t=GridDimensionConfig(
                d=self.entry_dt.value(),
                N=self.entry_Nt.value(),
                unit="s",
            ),
            mask=numpy.array(self.well_grid_items_selected)
        )
    
    @TypecheckFunction
    def get_af_software_is_enabled(self)->bool:
        return self.interactive_widgets.checkbox_laserAutofocus.checkState()==Qt.Checked
    
    @TypecheckFunction
    def get_af_software_channel(self,only_when_enabled:bool=True)->Optional[str]:
        if only_when_enabled and not self.get_af_software_is_enabled():
            return None
        
        return self.af_software_channel_names[self.af_channel_dropdown.currentIndex()]
    
    @TypecheckFunction
    def get_af_laser_is_enabled(self)->bool:
        return self.interactive_widgets.checkbox_laserAutofocus.checkState()==Qt.Checked

    @TypecheckFunction
    def set_af_laser_is_enabled(self,af_laser_on:bool):
        self.interactive_widgets.checkbox_laserAutofocus.setCheckState(Qt.Checked if af_laser_on else Qt.Unchecked)
    
    @TypecheckFunction
    def set_selected_channels(self,new_selection:List[str]):
        for item_index in range(len(self.list_channel_names)):
            item=self.list_configurations.item(item_index)
            item.setSelected(item.text() in new_selection)

        # todo change order as well! (new_selection is ordered)
    
    @TypecheckFunction
    def get_selected_channels(self)->List[str]:
        """
        return list of selected channels in order (ordered as displayed, will also be imaged in this order)
        """
        # get list of selected items (not necessarily ordered!)
        selected_channel_list:List[str]=[item.text() for item in self.list_configurations.selectedItems()]

        # in currently ordered list, return the selected elements
        imaging_channel_list=[channel for channel in self.list_channel_names if channel in selected_channel_list]

        return imaging_channel_list
    
    def set_image_file_format(self,new_format:ImageFormat):
        self.image_format_widget.setCurrentIndex(list(ImageFormat).index(new_format))
    
    def get_image_file_format(self)->ImageFormat:
        return list(ImageFormat)[self.image_format_widget.currentIndex()]

    @TypecheckFunction
    def grid_changed(self,Nxy_has_changed:bool=True):
        """ is called with new value if nx/ny changes """

        if Nxy_has_changed:
            size=QDesktopWidget().width()*0.06

            nx=self.entry_NX.value()
            ny=self.entry_NY.value()

            if self.well_grid_selector is None:
                self.well_grid_selector=BlankWidget(
                    height=size,
                    width=size,
                    background_color="black",
                    children=[],
                    tooltip="Grid imaging mask.\n\nSelected positions (lightblue) will be imaged inside each well.",
                )
                self.well_grid_selector.setFixedSize(size,size)

            self.well_grid_items_selected=[
                [
                    False 
                    for _c
                    in range(nx)
                ]
                for _r
                in range(ny)
            ]
            self.well_grid_items=[
                [
                    None
                    for _c
                    in range(nx)
                ]
                for _r
                in range(ny)
            ]

            # 1px between items
            item_width=int((size-(nx-1))//nx)
            item_height=int((size-(ny-1))//ny)
            for c in range(nx):
                for r in range(ny):
                    new_item=BlankWidget(
                        height=item_height,
                        width=item_width,
                        offset_top=r*item_height+r,
                        offset_left=c*item_width+c,
                        on_mousePressEvent=lambda event_data,r=r,c=c:self.toggle_well_grid_selection(event_data,row=r,column=c) or self.grid_changed(False)
                    )
                    self.well_grid_items[r][c]=new_item
                    self.toggle_well_grid_selection(_event_data=None,row=r,column=c)

            self.well_grid_selector.set_children(flatten(self.well_grid_items))

        self.position_mask_has_changed.emit()

    @TypecheckFunction
    def toggle_well_grid_selection(self,_event_data:Any,row:int,column:int,override_selected_state:Optional[bool]=None):
        grid_item=self.well_grid_items[row][column]
        is_currently_selected=self.well_grid_items_selected[row][column]
        if not override_selected_state is None:
            is_currently_selected=not override_selected_state # invert because if statement below toggles state

        if is_currently_selected:
            grid_item.background_color=UNSELECTED_GRID_POSITION_COLOR
            self.well_grid_items_selected[row][column]=False
        else:
            grid_item.background_color=SELECTED_GRID_POSITION_COLOR
            self.well_grid_items_selected[row][column]=True

        grid_item.generate_stylesheet()

    @TypecheckFunction
    def channel_list_rows_moved(self,_parent:QModelIndex,row_range_moved_start:int,row_range_moved_end:int,_destination:QModelIndex,row_index_drop_release:int):
        # saved items about to be moved
        dragged=self.list_channel_names[row_range_moved_start:row_range_moved_end+1]
        dragged_range_len=len(dragged)

        # remove range that is about to be moved
        ret_list=self.list_channel_names[:row_range_moved_start]
        ret_list.extend(self.list_channel_names[row_range_moved_end+1:])
        self.list_channel_names=ret_list

        # insert items at insert index, adjusted for removed range
        if row_index_drop_release<=row_range_moved_start:
            insert_index=row_index_drop_release
        else:
            insert_index=row_index_drop_release-dragged_range_len

        for i in reversed(range(dragged_range_len)):
            self.list_channel_names.insert(insert_index,dragged[i])

    @TypecheckFunction
    def set_saving_dir(self,_state:Any=None):
        save_dir_base = FileDialog(mode="open_dir",caption="Select base directory").run()
        if save_dir_base!="":
            self.lineEdit_baseDir.setText(save_dir_base)
            self.base_path_is_set = True

    @TypecheckFunction
    def toggle_acquisition(self,_pressed:bool):
        if not self.acquisition_is_running:
            # make sure all the parameters are fine
            _=self.start_experiment(dry=True)
            
            self.acquisition_is_running=True

            self.btn_startAcquisition.setText(ComponentLabels.BUTTON_START_ACQUISITION_RUNNING_TEXT)

            self.experiment_finished_signal=self.start_experiment(dry=False)
            self.experiment_config_data=self.experiment_finished_signal.acquisition_config

            if self.experiment_finished_signal.type=="done":
                self.acquisition_is_finished()
                return
            elif self.experiment_finished_signal.type=="exception":
                self.acquisition_is_running=False
                self.btn_startAcquisition.setText(ComponentLabels.BUTTON_START_ACQUISITION_IDLE_TEXT)
                return

            # else: self.experiment_finished_signal.type=="async"

            self.experiment_finished_signal.connect(self.acquisition_is_finished)

            QApplication.processEvents()
        else:
            # try this because multipoint worker may run synchronously, in which case there is no signal to disconnect (so disconnecting will throw)
            try:
                self.experiment_finished_signal.disconnect(self.acquisition_is_finished)
            except:
                pass
            
            self.acquisition_is_finished(aborted=True)

    @TypecheckFunction
    def acquisition_is_finished(self,aborted:bool=False):
        self.acquisition_is_running=False
        self.btn_startAcquisition.setText(ComponentLabels.BUTTON_START_ACQUISITION_IDLE_TEXT)

        self.experiment_finished_signal=None

        if aborted:
            self.abort_experiment()
            MessageBox(title="Acquisition terminated",text="Acquisition was terminated. It may take a few seconds until the microscope has finished the last step is was working on.",mode="information").run()
        else:
            if QMessageBox.Open==MessageBox(title="Acquisition finished",text="Acquisition is finished. See progress bar for details.\n\nClick 'Open' button to open experiment output folder.",mode="information",button_override=QMessageBox.Ok|QMessageBox.Open).run():
                # linux only (unsure if other things are linux only so far, but this is definitely one of them)
                subprocess.Popen(f'xdg-open {os.path.realpath(self.experiment_config_data.output_path)}'.split(" "))

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.storage_widget,
            self.grid_widget,

            self.checkbox_withAutofocus,
            self.af_channel_dropdown,
            self.btn_startAcquisition,
            self.list_configurations,

            *([self.interactive_widgets.checkbox_laserAutofocus] if self.is_laser_af_initialized else []),
        ]
    
    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        for widget in self.get_all_interactive_widgets():
            if not widget in exceptions:
                widget.setEnabled(set_enabled)
