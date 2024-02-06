# qt libraries
from qtpy.QtWidgets import QFrame, QDoubleSpinBox, QSpinBox, QGridLayout, QLabel

import pyqtgraph as pg

from control._def import *
from control.gui import *
from control.core import LaserAutofocusController, ConfigurationManager, LiveController

from .live_control import LiveControlWidget
from .laser_autofocus import LaserAutofocusControlWidget

from typing import Optional, Union, List, Tuple

NZ_LABEL='num images'
DZ_LABEL='delta Z (um)'
DZ_TOOLTIP="""use autofocus by taking z-stack of images (NZ images, with dz um distance between images), then
calculating a focus metric and choosing the image plane with the best metric.

the images are taken in the channel that is currently selected for live view (led+micro will be turned on if they are off)

this will take a few seconds"""

LASER_AUTOFOCUS_PANEL_TITLE="Laser Reflection Autofocus"
SOFTWARE_AUTOFOCUS_PANEL_TITLE="Software Autofocus"

DEFAULT_NZ=10
DEFAULT_DELTAZ=1.5

class SoftwareAutoFocusWidget(QFrame):
    def __init__(self,
        software_af_controller,
        configuration_manager,
        on_set_all_interactible_enabled:Callable[[bool,],None]
    ):
        super().__init__()

        self.software_af_controller=software_af_controller
        self.configuration_manager=configuration_manager
        self.on_set_all_interactible_enabled=on_set_all_interactible_enabled

        self.entry_delta = SpinBoxDouble(minimum=0.1,maximum=20.0,step=0.1,num_decimals=3,default=DEFAULT_DELTAZ,keyboard_tracking=False).widget
        self.entry_N = SpinBoxInteger(minimum=3,maximum=23,step=2,default=DEFAULT_NZ,keyboard_tracking=False).widget

        self.btn_autofocus = Button("Run",default=False,checkable=True,checked=False,tooltip=DZ_TOOLTIP,on_clicked=self.autofocus_start).widget

        self.channel_dropdown=Dropdown(
            items=[config.name for config in self.configuration_manager.configurations],
            current_index=0,
        ).widget

        # layout
        qtlabel_dz=Label(DZ_LABEL,tooltip=DZ_TOOLTIP).widget
        qtlabel_Nz=Label(NZ_LABEL,tooltip=DZ_TOOLTIP).widget
        
        self.grid = Grid(
            [ qtlabel_dz, self.entry_delta, qtlabel_Nz, self.entry_N, self.channel_dropdown, self.btn_autofocus ]
        ).layout
        self.setLayout(self.grid)

    def autofocus_start(self,_btn_state):
        self.on_set_all_interactible_enabled(False)
        self.software_af_controller.autofocusFinished.connect(self.autofocus_is_finished)

        dz_um:float=self.entry_delta.value()
        dz_mm:float=dz_um*1e-3

        self.software_af_controller.autofocus(
            self.configuration_manager.configurations[self.channel_dropdown.currentIndex()],
            N=self.entry_N.value(),
            dz_mm=dz_mm,
        )

    def autofocus_is_finished(self):
        self.software_af_controller.autofocusFinished.disconnect(self.autofocus_is_finished)
        self.btn_autofocus.setChecked(False)
        self.on_set_all_interactible_enabled(True)

def create_empty_image_display(
    invert_y:bool=False
):
    graph_display=pg.GraphicsLayoutWidget()
    graph_display.view = graph_display.addViewBox()
    graph_display.img = pg.ImageItem(border='w')
    graph_display.view.addItem(graph_display.img)
    graph_display.view.setAspectLocked(True)

    if invert_y:
        graph_display.view.invertY()

    return graph_display

class LaserAfDebugdisplay:
    def __init__(self,
        laser_af_controller:LaserAutofocusController,
    ):
        self.laser_af_controller=laser_af_controller

        self.image_display=create_empty_image_display()

        max_pix_value=2**16
        temp_image=numpy.array([[0,max_pix_value//4],[max_pix_value//2,max_pix_value]],numpy.uint16)
        self.display_image(temp_image)

        self.live_controller=self.laser_af_controller.camera.wrapper.live_controller
        self.live_control_widget=LiveControlWidget(
            liveController=self.live_controller,
            configuration_manager=ConfigurationManager("channel_config_focus_camera.json"),
            on_new_frame=self.display_image
        )

        self.laser_af_fitness_display=pg.GraphicsLayoutWidget()
        self.laser_af_fitness_display.view=self.laser_af_fitness_display.addViewBox()
        self.laser_af_fitness_test_range=SpinBoxDouble(minimum=50.0,maximum=700.0,default=400.0,step=10.0).widget
        self.laser_af_fitness_test_steps=SpinBoxInteger(minimum=3,maximum=41,default=11,step=2).widget
        self.run_laser_af_fitness_test=Button("run Laser Reflection Autofocus test",on_clicked=lambda _btn:self.run_laser_af_test())

        self.sensor_crop_full_button=Button("remove sensor crop",on_clicked=lambda _btn:self.uncrop_sensor())
        self.sensor_crop_partial_button=Button("crop sensor",on_clicked=lambda _btn:self.crop_sensor())

        self.exposure_time_ms_input=SpinBoxDouble(minimum=1.0,maximum=50.0,default=self.laser_af_controller.liveController.currentConfiguration.exposure_time_ms,
            on_valueChanged=self.set_exposure_time).widget

        self.widget=HBox(
            self.image_display,
            VBox(
                self.live_control_widget,
                HBox(
                    Label("exposure time (ms)"),
                    self.exposure_time_ms_input
                ),
                HBox(
                    self.sensor_crop_full_button,
                    self.sensor_crop_partial_button
                ),
                HBox(
                    Label("z range"),
                    self.laser_af_fitness_test_range,
                    Label("total steps"),
                    self.laser_af_fitness_test_steps
                ),
                self.run_laser_af_fitness_test,
                self.laser_af_fitness_display
            )
        ).widget

    def set_exposure_time(self,new_exposure_time_ms:float):
        print(f"changed laser autofocus exposure time from {self.laser_af_controller.liveController.currentConfiguration.exposure_time_ms:.2f} to {new_exposure_time_ms:.2f}")
        self.laser_af_controller.liveController.currentConfiguration.exposure_time_ms=new_exposure_time_ms

    def get_current_sensor_settings(self)->dict:
        sensor_settings=dict(
            offset_x=self.laser_af_controller.camera.camera.OffsetX.get(),
            offset_y=self.laser_af_controller.camera.camera.OffsetY.get(),
            height=self.laser_af_controller.camera.camera.Height.get(),
            width=self.laser_af_controller.camera.camera.Width.get(),
        )
        return sensor_settings

    def uncrop_sensor(self):
        sensor_settings=self.get_current_sensor_settings()
        self.cropped_sensor_settings=sensor_settings
        print(f"old sensor settings: {sensor_settings}")

        self.laser_af_controller.camera.set_ROI(
            offset_x=0,
            offset_y=0,
            width=self.laser_af_controller.camera.camera.WidthMax.get(),
            height=self.laser_af_controller.camera.camera.HeightMax.get()
        )

        sensor_settings=self.get_current_sensor_settings()
        print(f"new sensor settings: {sensor_settings}")

    def crop_sensor(self):
        restored_settings=self.cropped_sensor_settings
        print(f"restoring sensor crop: {restored_settings}")

        self.laser_af_controller.camera.set_ROI(
            offset_x=restored_settings["offset_x"],
            offset_y=restored_settings["offset_y"],
            width=restored_settings["width"],
            height=restored_settings["height"],
        )
        restored_settings=self.get_current_sensor_settings()
        print(f"restoring sensor crop: {restored_settings}")

        print(f"{self.laser_af_controller.liveController.currentConfiguration.exposure_time_ms=}")

    def run_laser_af_test(self):
        z_range_um=self.laser_af_fitness_test_range.value()
        z_range_mm=z_range_um/1000
        num_steps=self.laser_af_fitness_test_steps.value()
        step_size_mm=z_range_mm/(num_steps-1)
        half_range_mm=z_range_mm/2

        real_displacements=numpy.zeros(num_steps)
        measured_displacement=numpy.zeros(num_steps)

        # move to bottom end of z test range, and clear backlash
        self.live_controller.microcontroller.move_z_usteps(
            usteps = self.live_controller.microcontroller.mm_to_ustep_z(
                value_mm = -half_range_mm 
            )
        )
        self.live_controller.microcontroller.wait_till_operation_is_completed()

        # then clear backlash
        self.live_controller.microcontroller.move_z_usteps( - self.live_controller.microcontroller.clear_z_backlash_usteps )
        self.live_controller.microcontroller.wait_till_operation_is_completed()
        self.live_controller.microcontroller.move_z_usteps( self.live_controller.microcontroller.clear_z_backlash_usteps )
        self.live_controller.microcontroller.wait_till_operation_is_completed()

        for i in range(num_steps):
            # first step has offset 0 from bottom of range 
            if i>0:
                self.live_controller.microcontroller.move_z_usteps(usteps=self.live_controller.microcontroller.mm_to_ustep_z(value_mm = step_size_mm))
                self.live_controller.microcontroller.wait_till_operation_is_completed()

            real_displacements[i] = -half_range_mm + i * step_size_mm
            measured_displacement[i] = self.laser_af_controller.measure_displacement()

        self.live_controller.microcontroller.move_z_usteps(usteps = self.live_controller.microcontroller.mm_to_ustep_z(value_mm = -half_range_mm))
        self.live_controller.microcontroller.wait_till_operation_is_completed()

        self.plot_displacement_test(
            real_displacement=real_displacements*1e3, # to rescale from mm to um
            measured_displacement=measured_displacement # this is in um
        )

    def plot_displacement_test(self,
        real_displacement,
        measured_displacement,
    ):  
        # clear existing plot (if exists)
        try:
            self.laser_af_fitness_display.plot_data.clear()
        except:
            pass

        bins=real_displacement
        for data,color in [
            (real_displacement,"green"),
            (measured_displacement,"orange"),
        ]:
            plot_kwargs={'x':bins,'y':data,'pen':pg.mkPen(color=color)}

            try:
                self.laser_af_fitness_display.plot_data.plot(**plot_kwargs)
            except:
                self.laser_af_fitness_display.plot_data=self.laser_af_fitness_display.addPlot(0,0,title="Laser Reflection Autofocus test",viewBox=self.laser_af_fitness_display.view,**plot_kwargs)

    def display_image(self,new_image:numpy.ndarray):
        kwargs={
            'autoLevels':False, # disable automatically scaling the image pixel values (scale so that the lowest pixel value is pure black, and the highest value if pure white)
        }
        if new_image.dtype==numpy.float32:
            self.image_display.img.setImage(new_image,levels=(0.0,1.0),**kwargs)
        else:
            self.image_display.img.setImage(new_image,**kwargs)
        

class AutofocusWidget:
    software_af_debug_display:Optional[QWidget]
    software_af_control:QWidget

    laser_af_debug_display:Optional[QWidget]
    laser_af_control:QWidget

    af_control:QWidget

    def __init__(self,
        laser_af_controller,
        software_af_controller,
        get_current_z_pos_in_mm,
        configuration_manager,
        on_set_all_interactible_enabled,

        laser_af_validity_changed:Signal,

        debug_laser_af:bool=False,
        debug_software_af:bool=False,
    ):
        if debug_software_af:
            self.software_af_debug_display=BlankWidget(background_color="black")
        else:
            self.software_af_debug_display=None

        self.software_af_control=SoftwareAutoFocusWidget(
            software_af_controller = software_af_controller,
            on_set_all_interactible_enabled = on_set_all_interactible_enabled,
            configuration_manager = configuration_manager
        )

        if debug_laser_af:
            self.laser_af_debug_display=LaserAfDebugdisplay(
                laser_af_controller=laser_af_controller
            ).widget
        else:
            self.laser_af_debug_display=None

        self.laser_af_control:LaserAutofocusControlWidget=LaserAutofocusControlWidget(
            laser_af_controller,
            get_current_z_pos_in_mm=get_current_z_pos_in_mm,
            laser_af_validity_changed=laser_af_validity_changed,
            focus_in_progress=lambda is_in_progress:on_set_all_interactible_enabled(not is_in_progress)
        )

        self.af_control=VBox(
            Dock(self.laser_af_control,LASER_AUTOFOCUS_PANEL_TITLE),
            Dock(self.software_af_control,SOFTWARE_AUTOFOCUS_PANEL_TITLE),
            
            with_margins=False,
        ).widget

    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return flatten(*[
            self.laser_af_control.get_all_interactive_widgets(),
            self.software_af_control,
        ])
    
    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        if not self.software_af_control in exceptions:
            self.software_af_control.setEnabled(set_enabled)

        if not self.laser_af_control in exceptions:
            self.laser_af_control.set_all_interactible_enabled(set_enabled,exceptions)


    
