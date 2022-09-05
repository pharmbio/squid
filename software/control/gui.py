# set QT_API environment variable
import os 
os.environ["QT_API"] = "pyqt5"
import qtpy

# qt libraries
from qtpy.QtCore import *
from qtpy.QtWidgets import *
from qtpy.QtGui import *

# app specific libraries
import control.widgets as widgets
import control.camera as camera
import control.core as core
import control.microcontroller as microcontroller
from control._def import *

import pyqtgraph.dockarea as dock

class OctopiGUI(QMainWindow):

	# variables
	fps_software_trigger = 100

	def __init__(self, is_simulation = False, *args, **kwargs):
		super().__init__(*args, **kwargs)

		# load objects
		if is_simulation:
			self.camera = camera.Camera_Simulation(rotate_image_angle=ROTATE_IMAGE_ANGLE,flip_image=FLIP_IMAGE)
			self.microcontroller = microcontroller.Microcontroller_Simulation()
		else:
			try:
				self.camera = camera.Camera(rotate_image_angle=ROTATE_IMAGE_ANGLE,flip_image=FLIP_IMAGE)
				self.camera.open()
			except:
				raise Exception("camera not found.")

			try:
				self.microcontroller = microcontroller.Microcontroller(version=CONTROLLER_VERSION)
			except:
				raise Exception("controller not found.")

		# configure the actuators
		self.microcontroller.configure_actuators()
			
		self.configurationManager = core.ConfigurationManager('./channel_configurations.xml')
		self.streamHandler =        core.StreamHandler(display_resolution_scaling=DEFAULT_DISPLAY_CROP/100)
		self.liveController = 		core.LiveController(self.camera,self.microcontroller,self.configurationManager)
		self.navigationController = core.NavigationController(self.microcontroller)
		self.autofocusController = 	core.AutoFocusController(self.camera,self.navigationController,self.liveController)
		self.multipointController = core.MultiPointController(self.camera,self.navigationController,self.liveController,self.autofocusController,self.configurationManager)
		if ENABLE_TRACKING:
			self.trackingController = core.TrackingController(self.camera,self.microcontroller,self.navigationController,self.configurationManager,self.liveController,self.autofocusController,self.imageDisplayWindow)
		self.imageSaver = core.ImageSaver(image_format=Acquisition.IMAGE_FORMAT)
		self.imageDisplay = core.ImageDisplay()

		# set up the camera
		self.camera.set_software_triggered_acquisition() #self.camera.set_continuous_acquisition()
		self.camera.set_callback(self.streamHandler.on_new_frame)
		self.camera.enable_callback()
		if ENABLE_STROBE_OUTPUT:
			self.camera.set_line3_to_exposure_active()

		# load window
		if ENABLE_TRACKING:
			self.imageDisplayWindow = core.ImageDisplayWindow(draw_crosshairs=True,autoLevels=AUTOLEVEL_DEFAULT_SETTING)
			self.imageDisplayWindow.show_ROI_selector()
		else:
			self.imageDisplayWindow = core.ImageDisplayWindow(draw_crosshairs=True,autoLevels=AUTOLEVEL_DEFAULT_SETTING)
		self.imageArrayDisplayWindow = core.ImageArrayDisplayWindow()

		# image display windows
		self.imageDisplayTabs = QTabWidget()
		self.imageDisplayTabs.addTab(self.imageDisplayWindow.widget, "Live View")
		self.imageDisplayTabs.addTab(self.imageArrayDisplayWindow.widget, "Multichannel Acquisition")

		# load widgets
		self.cameraSettingWidget = 	  widgets.CameraSettingsWidget(self.camera,include_gain_exposure_time=False)
		self.liveControlWidget = 	  widgets.LiveControlWidget(self.streamHandler,self.liveController,self.configurationManager,show_trigger_options=True,show_display_options=True,show_autolevel=SHOW_AUTOLEVEL_BTN,autolevel=AUTOLEVEL_DEFAULT_SETTING)
		self.navigationWidget = 	  widgets.NavigationWidget(self.navigationController)
		self.dacControlWidget = 	  widgets.DACControWidget(self.microcontroller)
		self.autofocusWidget = 		  widgets.AutoFocusWidget(self.autofocusController)
		self.recordingControlWidget = widgets.RecordingWidget(self.streamHandler,self.imageSaver)
		if ENABLE_TRACKING:
			self.trackingControlWidget = widgets.TrackingControllerWidget(self.trackingController,self.configurationManager,show_configurations=TRACKING_SHOW_MICROSCOPE_CONFIGURATIONS)
		self.multiPointWidget =          widgets.MultiPointWidget(self.multipointController,self.configurationManager)

		self.recordTabWidget = QTabWidget()
		if ENABLE_TRACKING:
			self.recordTabWidget.addTab(self.trackingControlWidget, "Tracking")
		self.recordTabWidget.addTab(self.recordingControlWidget, "Simple Recording")
		self.recordTabWidget.addTab(self.multiPointWidget, "Multipoint Acquisition")
		
		# transfer the layout to the central widget
		self.centralWidget = QWidget()
		self.centralWidget.setLayout(self.generateCentralWidgetLayout())
		self.centralWidget.setFixedWidth(self.centralWidget.minimumSizeHint().width())
		
		# setup window layout
		self.setCentralWidget(self.generateMainDockArea())
		desktopWidget = QDesktopWidget()
		height_min = 0.9*desktopWidget.height()
		width_min = 0.96*desktopWidget.width()
		self.setMinimumSize(width_min,height_min)

		# make connections
		self.setupConnections()

	def generateCentralWidgetLayout(self):
		# layout widgets
		layout = QVBoxLayout()
		layout.addWidget(self.cameraSettingWidget)
		layout.addWidget(self.liveControlWidget)
		layout.addWidget(self.navigationWidget)
		if SHOW_DAC_CONTROL:
			layout.addWidget(self.dacControlWidget)
		layout.addWidget(self.autofocusWidget)
		layout.addWidget(self.recordTabWidget)
		layout.addStretch()

		return layout

	def generateMainDockArea(self):
		dock_display = dock.Dock('Image Display', autoOrientation = False)
		dock_display.showTitleBar()
		dock_display.addWidget(self.imageDisplayTabs)
		dock_display.setStretch(x=100,y=None)
		dock_controlPanel = dock.Dock('Controls', autoOrientation = False)
		# dock_controlPanel.showTitleBar()
		dock_controlPanel.addWidget(self.centralWidget)
		dock_controlPanel.setStretch(x=1,y=None)
		dock_controlPanel.setFixedWidth(dock_controlPanel.minimumSizeHint().width())
		main_dockArea = dock.DockArea()
		main_dockArea.addDock(dock_display)
		main_dockArea.addDock(dock_controlPanel,'right')

		return main_dockArea

	def setupConnections(self):
		self.streamHandler.signal_new_frame_received.connect(self.liveController.on_new_frame)
		self.streamHandler.image_to_display.connect(self.imageDisplay.enqueue)
		self.streamHandler.packet_image_to_write.connect(self.imageSaver.enqueue)
		self.imageDisplay.image_to_display.connect(self.imageDisplayWindow.display_image) # may connect streamHandler directly to imageDisplayWindow
		self.navigationController.xPos.connect(self.navigationWidget.label_Xpos.setNum)
		self.navigationController.yPos.connect(self.navigationWidget.label_Ypos.setNum)
		self.navigationController.zPos.connect(self.navigationWidget.label_Zpos.setNum)
		if ENABLE_TRACKING:
			self.navigationController.signal_joystick_button_pressed.connect(self.trackingControlWidget.slot_joystick_button_pressed)
		else:
			self.navigationController.signal_joystick_button_pressed.connect(self.autofocusController.autofocus)
		self.autofocusController.image_to_display.connect(self.imageDisplayWindow.display_image)
		self.multipointController.image_to_display.connect(self.imageDisplayWindow.display_image)
		self.multipointController.signal_current_configuration.connect(self.liveControlWidget.set_microscope_mode)
		self.multipointController.image_to_display_multi.connect(self.imageArrayDisplayWindow.display_image)
		self.liveControlWidget.signal_newExposureTime.connect(self.cameraSettingWidget.set_exposure_time)
		self.liveControlWidget.signal_newAnalogGain.connect(self.cameraSettingWidget.set_analog_gain)
		self.liveControlWidget.update_camera_settings()
		self.liveControlWidget.signal_autoLevelSetting.connect(self.imageDisplayWindow.set_autolevel)

	def closeEvent(self, event):
		event.accept()
		# self.softwareTriggerGenerator.stop() @@@ => 
		self.navigationController.home()
		self.liveController.stop_live()
		self.camera.close()
		self.imageSaver.close()
		self.imageDisplay.close()
		self.microcontroller.close()
