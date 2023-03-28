from qtpy.QtCore import Signal
from qtpy.QtWidgets import QApplication, QFrame, QLabel, QDoubleSpinBox, QGridLayout

from control.core import LaserAutofocusController, LaserAutofocusData
from control.gui import *

SET_REFERENCE_BUTTON_TEXT_IDLE="Set as reference plane"
SET_REFERENCE_BUTTON_TEXT_IN_PROGRESS="setting reference plane (in progress)"
INITIALIZE_BUTTON_TEXT_IDLE="Initialize"
INITIALIZE_BUTTON_TEXT_IN_PROGRESS="initializing (in progress)"
MEASURE_DISPLACEMENT_BUTTON_TEXT_IDLE="Measure displacement"
MEASURE_DISPLACEMENT_BUTTON_TEXT_IN_PROGRESS="Measure displacement (in progress)"
MOVE_TO_TARGET_BUTTON_TEXT_IDLE="Move to target"
MOVE_TO_TARGET_BUTTON_TEXT_IN_PROGRESS="Move to target (in progress)"
DEINITIALIZE_BUTTON_TEXT="Deinitialize (!)"

BTN_INITIALIZE_TOOLTIP="""
Prepare the Laser Autofocus system to work with the current plate type

This only needs to be done once after program start-up \n(or after putting a new plate type into the microscope. It does not need to be re-run after putting a new plate of the same type on the microscope though.)

If the Laser AF system is initialized while cells are not in focus, the system may not function reliably.
It is therefore recommended to initialize the system immediately before the first reference is set, i.e. \n\tafter program start, bring cells into focus, click this button, then set the reference plane afterwards.

Loading the Laser AF data from a configuration file will also load this data, so\nafter loading a file that includes Laser AF data, there is no need to click this button.

Note: If you press this button after you previously pressed 'set as reference', you will need to set a reference again.
"""
BTN_SET_REFERENCE_TOOLTIP="""
Set z reference plane

The Laser AF system can focus on cells without bleaching them by effectively measuring the distance between the bottom of the well plate and the objective.
The bottom of a well plate is not strictly flat, and can vary from the lowest to the highest point across the whole plate by about 200um.

To compensate for that, the Laser AF system needs to know what the ideal distance between the objective and the bottom of the well plate should be.
Clicking this button measures this distance, and saves it for later reference.

When the Laser AF is actually 'used' later, it measures the new distance between the objective and the bottom of the well plate, and then moves the objective so 
that the distance matches the distance set by this reference.

Note: The Laser AF needs to have been initialized before a reference plane can be set. 
      Initializing the Laser AF system again after a reference has already been set also invalidates the reference, i.e. a new reference needs to be set.
"""
BTN_MEASURE_DISPLACEMENT_TOOLTIP="""
Measure the distance between the objective and the bottom the wellplate

As explained in the tooltip of the 'set as reference' button, this button calculates the difference between the currently measured and ideal distance between the objective and the bottom of the well plate.
"""
BTN_MOVE_TO_TARGET_TOOLTIP="""
Move the objective so that the distance between the objective and the bottom of the well plate is a certain number higher/lower than the ideal distance measured by the reference.

The difference in distance is determined by the text box on the left.

A difference of zero means that on 'move to target', the objective is moved so that the distance between the objective and the bottom of the wellplate is exactly the same distance as in the reference.
"""
BTN_DEINITIALIZE_TOOLTIP="""
Deinitialize laser af config.

WARNING: This will remove all laser af related configuration that was created since program start-up.
         Laser AF initialization data needs to be recreated after this button has been clicked.

You will be asked to confirm this action if you click this button.

Primarily used to clear laser af config data so that other data can be read from a config file (which by design will not overwrite existing data)
"""
BTN_MOVE_Z_REF_TEXT="Move to Z reference"
BTN_MOVE_Z_REF_TOOLTIP="""
Move to Z reference

When the laser AF reference was set, the Z height of the reference was saved internally.
Clicking this button allows you to return to this height.

Note: This height should be _close_ to the focus plane, but might not be the focus plane directly.
      It should allow you to move to this reference height, and then reliably focus on a single 'move to target' button click afterwards.

e.g. To load a new plate, you need to enter and then leave the loading position.
     By design, leaving the loading position will NOT automatically return to the z reference (in fact, it might be quite far off), hence this button.
"""

class LaserAutofocusControlWidget(QFrame):
    def __init__(self,
        laserAutofocusController:LaserAutofocusController,
        get_current_z_pos_in_mm:Callable[[None,],float],
        laser_af_validity_changed:Signal,
        focus_in_progress:Callable[[bool],None]
    ):
        super().__init__()

        self.laserAutofocusController = laserAutofocusController
        self.get_current_z_pos_in_mm = get_current_z_pos_in_mm
        self.laser_af_validity_changed = laser_af_validity_changed
        self.on_focus_in_progress=focus_in_progress

        self.btn_initialize = Button(INITIALIZE_BUTTON_TEXT_IDLE,checkable=False,checked=False,default=False,tooltip=BTN_INITIALIZE_TOOLTIP,on_clicked=self.initialize).widget
        self.btn_set_reference = Button(SET_REFERENCE_BUTTON_TEXT_IDLE,checkable=False,checked=False,default=False,tooltip=BTN_SET_REFERENCE_TOOLTIP,on_clicked=self.set_reference).widget
        self.btn_move_z_ref = Button(
            BTN_MOVE_Z_REF_TEXT,
            checkable=False,
            tooltip=BTN_MOVE_Z_REF_TOOLTIP,
            on_clicked=self.move_to_ref_z
        ).widget

        self.label_displacement = QLabel()
        self.laserAutofocusController.signal_displacement_um.connect(lambda displacement_um:self.label_displacement.setText(f"{displacement_um:9.3f}"))

        self.btn_measure_displacement = Button(MEASURE_DISPLACEMENT_BUTTON_TEXT_IDLE,checkable=False,checked=False,default=False,tooltip=BTN_MEASURE_DISPLACEMENT_TOOLTIP,on_clicked=self.measure_displacement).widget

        self.entry_target = SpinBoxDouble(minimum=-100.0,maximum=100.0,step=0.01,num_decimals=2,default=0.0,keyboard_tracking=False).widget
        self.btn_move_to_target = Button(MOVE_TO_TARGET_BUTTON_TEXT_IDLE,checkable=False,checked=False,default=False,tooltip=BTN_MOVE_TO_TARGET_TOOLTIP,on_clicked=self.move_to_target).widget

        self.grid = Grid(
            [
                self.btn_initialize,
                self.btn_move_z_ref,
                self.btn_set_reference,
            ],
            [
                QLabel('Displacement (um)'),
                self.label_displacement,
                self.btn_measure_displacement,
            ],
            [
                QLabel('Target (um)'),
                self.entry_target,
                self.btn_move_to_target,
            ],
        ).layout

        self.grid.setRowStretch(self.grid.rowCount(), 1)

        self.setLayout(self.grid)

        self.has_been_initialized=False
        self.reference_was_set=False

        self.deinitialize(require_confirmation=False)

    def move_to_ref_z(self,_btn=None):
        self.on_focus_in_progress(True)
        self.laserAutofocusController.navigation.move_z_to(z_mm=self.laserAutofocusController.reference_z_height_mm,wait_for_completion={})
        self.on_focus_in_progress(False)

    def deinitialize(self,_btn_state=None,require_confirmation:bool=True):
        if require_confirmation:
            answer=MessageBox(title="Deinitialize laser AF?",mode="question",text="are you sure you want to deinitialize the laser AF?\nthis will require you to perform the initialization procedure again (or to load reference data from a file)\nClick Yes to clear the laser af initialization data.").run()
            if answer!=QMessageBox.Yes:
                return

        self.laserAutofocusController.is_initialized=False
        self.laserAutofocusController.x_reference = None
        self.laserAutofocusController.reset_camera_sensor_crop()

        # with no initialization and no reference, not allowed to do anything
        self.btn_set_reference.setDisabled(True)
        self.btn_set_reference.setText(SET_REFERENCE_BUTTON_TEXT_IDLE)
        self.btn_measure_displacement.setDisabled(True)
        self.btn_measure_displacement.setText(MEASURE_DISPLACEMENT_BUTTON_TEXT_IDLE)
        self.btn_move_to_target.setDisabled(True)
        self.btn_move_to_target.setText(MOVE_TO_TARGET_BUTTON_TEXT_IDLE)
        self.btn_move_z_ref.setDisabled(True)
        self.entry_target.setDisabled(True)

        self.laser_af_validity_changed.emit(False) # signal that laser af is now invalid

    def initialize(self):
        """ automatically initialize laser autofocus """

        self.on_focus_in_progress(True)

        self.btn_initialize.setDisabled(True)
        self.btn_initialize.setText(INITIALIZE_BUTTON_TEXT_IN_PROGRESS)
        QApplication.processEvents() # process GUI events, i.e. actually display the changed text etc.

        try:
            self.laserAutofocusController.initialize_auto()
            initialization_error=None
        except Exception as e:
            initialization_error=e

        self.btn_initialize.setDisabled(False)
        self.btn_initialize.setText(INITIALIZE_BUTTON_TEXT_IDLE)

        if not initialization_error is None:
            MessageBox(title="Could not initialize laser AF",mode="information",text=f"there was a problem initializing the laser autofocus. is the plate in focus? {initialization_error=}").run()
            return

        self.on_focus_in_progress(False)

        self.call_after_initialization()

    def call_after_initialization(self):

        # allow setting of a reference after initialization
        self.has_been_initialized=True

        # re-initialization may invalidate reference
        self.reference_was_set=False
        self.btn_set_reference.setDisabled(False)
        self.btn_set_reference.setText(SET_REFERENCE_BUTTON_TEXT_IDLE)

        self.laser_af_validity_changed.emit(False) # when re-initialized, the previous reference is stale (i.e. invalid)

        self.btn_measure_displacement.setText(MEASURE_DISPLACEMENT_BUTTON_TEXT_IDLE)
        self.btn_measure_displacement.setDisabled(True)
        self.btn_move_to_target.setText(MOVE_TO_TARGET_BUTTON_TEXT_IDLE)
        self.btn_move_to_target.setDisabled(True)

        QApplication.processEvents() # process GUI events, i.e. actually display the changed text etc.

    def set_reference(self):
        self.on_focus_in_progress(True)

        self.btn_set_reference.setDisabled(True)
        self.btn_set_reference.setText(SET_REFERENCE_BUTTON_TEXT_IN_PROGRESS)

        self.laserAutofocusController.set_reference(z_pos_mm=self.get_current_z_pos_in_mm())

        self.on_focus_in_progress(False)

        # allow actual use of laser AF now
        self.call_after_set_reference()

    def call_after_set_reference(self):

        self.btn_set_reference.setDisabled(False)
        self.btn_set_reference.setText(SET_REFERENCE_BUTTON_TEXT_IDLE)

        self.btn_move_z_ref.setDisabled(False)

        self.reference_was_set=True

        self.btn_measure_displacement.setDisabled(False)
        self.btn_measure_displacement.setText(MEASURE_DISPLACEMENT_BUTTON_TEXT_IDLE)

        self.btn_move_to_target.setDisabled(False)
        self.btn_move_to_target.setText(MOVE_TO_TARGET_BUTTON_TEXT_IDLE)
        self.entry_target.setDisabled(False)

        self.laser_af_validity_changed.emit(True) # signal that laser af is now valid

    def measure_displacement(self):
        self.btn_measure_displacement.setDisabled(True)
        self.btn_measure_displacement.setText(MEASURE_DISPLACEMENT_BUTTON_TEXT_IN_PROGRESS)
        QApplication.processEvents() # process GUI events, i.e. actually display the changed text etc.
        
        self.laserAutofocusController.measure_displacement()

        self.btn_measure_displacement.setDisabled(False)
        self.btn_measure_displacement.setText(MEASURE_DISPLACEMENT_BUTTON_TEXT_IDLE)

    def move_to_target(self,_btn=None,target_um=None):
        self.on_focus_in_progress(True)

        self.btn_move_to_target.setDisabled(True)
        self.btn_move_to_target.setText(MOVE_TO_TARGET_BUTTON_TEXT_IN_PROGRESS)
        QApplication.processEvents() # process GUI events, i.e. actually display the changed text etc.

        if target_um is None:
            target_um=self.entry_target.value()
        self.laserAutofocusController.move_to_target(target_um)
        self.laserAutofocusController.measure_displacement()

        self.btn_move_to_target.setDisabled(False)
        self.btn_move_to_target.setText(MOVE_TO_TARGET_BUTTON_TEXT_IDLE)

        self.on_focus_in_progress(False)
    
    @TypecheckFunction
    def get_reference_data(self)->LaserAutofocusData:
        return LaserAutofocusData(
            x_reference=self.laserAutofocusController.x_reference,
            um_per_px=self.laserAutofocusController.um_per_px,

            z_um_at_reference=self.laserAutofocusController.reference_z_height_mm*1e3,

            x_offset=self.laserAutofocusController.x_offset,
            y_offset=self.laserAutofocusController.y_offset,
            x_width=self.laserAutofocusController.width,
            y_width=self.laserAutofocusController.height,

            has_two_interfaces=self.laserAutofocusController.has_two_interfaces,
            use_glass_top=self.laserAutofocusController.use_glass_top,
        )
    
    @TypecheckFunction
    def set_reference_data(self,reference:Optional[LaserAutofocusData]):
        """ load reference data only if data is present """

        if reference is None:
            return

        self.laserAutofocusController.initialize_manual(
            x_offset=reference.x_offset,
            y_offset=reference.y_offset,
            width=reference.x_width,
            height=reference.y_width,
            um_per_px=reference.um_per_px,
            x_reference=reference.x_reference
        )

        self.laserAutofocusController.x_reference=reference.x_reference

        self.laserAutofocusController.has_two_interfaces=reference.has_two_interfaces
        self.laserAutofocusController.use_glass_top=reference.use_glass_top

        self.call_after_initialization()
        self.call_after_set_reference()

        self.laser_af_validity_changed.emit(True)

        self.laserAutofocusController.reference_z_height_mm=reference.z_um_at_reference/1e3

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.btn_initialize,
            self.btn_move_z_ref,
            self.btn_set_reference,
            self.btn_measure_displacement,
            self.btn_move_to_target,
        ]

    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        for widget in self.get_all_interactive_widgets():
            if not widget in exceptions:
                if set_enabled and widget is self.btn_set_reference:
                    if self.has_been_initialized:
                        self.btn_set_reference.setEnabled(True)
                elif set_enabled and widget in (self.btn_measure_displacement, self.btn_move_to_target):
                    if self.reference_was_set:
                        widget.setEnabled(True)
                else:
                    widget.setEnabled(set_enabled)