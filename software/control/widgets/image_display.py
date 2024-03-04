# qt libraries
from qtpy.QtCore import QObject, Signal, Qt # type: ignore
from qtpy.QtWidgets import QMainWindow, QWidget, QGridLayout, QDesktopWidget, QVBoxLayout, QLabel, QApplication, QSizePolicy

from control._def import *
from control.gui import Label, Grid, VBox, Button, HBox, Checkbox, BlankWidget

from control.core import ConfigurationManager

import numpy
import pyqtgraph as pg

from typing import Optional, List, Union, Tuple

class ImageDisplayWindow(QMainWindow):

    def __init__(self, window_title='', draw_crosshairs = False, show_LUT=False):
        super().__init__()
        self.setWindowTitle(window_title)
        self.setWindowFlags(self.windowFlags() | Qt.CustomizeWindowHint) # type: ignore
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint) # type: ignore
        self.show_LUT = show_LUT

        # interpret image data as row-major instead of col-major
        pg.setConfigOptions(imageAxisOrder='row-major')

        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.graphics_widget.view = self.graphics_widget.addViewBox()
        self.graphics_widget.view.invertY()
        
        ## lock the aspect ratio so pixels are always square
        self.graphics_widget.view.setAspectLocked(True)
        
        ## Create image item
        if self.show_LUT:
            self.graphics_widget.view = pg.ImageView()
            self.graphics_widget.img = self.graphics_widget.view.getImageItem()
            self.graphics_widget.img.setBorder('w')
            self.graphics_widget.view.ui.roiBtn.hide()
            self.graphics_widget.view.ui.menuBtn.hide()
            # self.LUTWidget = self.graphics_widget.view.getHistogramWidget()
            # self.LUTWidget.autoHistogramRange()
        else:
            self.graphics_widget.img = pg.ImageItem(border='w')
            self.graphics_widget.view.addItem(self.graphics_widget.img)
            max_state=[[-1011.6942184540692, 4011.694218454069], [-147.79939172464378, 3147.799391724644]] # furthest zoomed out
            min_state=[[1105.2084826209198, 1163.5473663736475], [1401.9018607761034, 1440.1751411998673]] # furthest zoomed in
            ((max_lowerx,max_upperx),(max_lowery,max_uppery))=max_state
            ((min_lowerx,min_upperx),(min_lowery,min_uppery))=min_state

            # restrict zooming and moving (part 2 of 2)
            self.graphics_widget.view.setLimits(
                xMin=max_lowerx,
                xMax=max_upperx,
                yMin=max_lowery,
                yMax=max_uppery,

                minXRange=min_upperx-min_lowerx,
                maxXRange=max_upperx-max_lowerx,
                minYRange=min_uppery-min_lowery,
                maxYRange=max_uppery-max_lowery,
            )

        ## Create ROI
        self.roi_pos = (500,500)
        self.roi_size = pg.Point(500,500)
        self.ROI = pg.ROI(self.roi_pos, self.roi_size, scaleSnap=True, translateSnap=True)
        self.ROI.setZValue(10)
        self.ROI.addScaleHandle((0,0), (1,1))
        self.ROI.addScaleHandle((1,1), (0,0))
        self.graphics_widget.view.addItem(self.ROI)
        self.ROI.hide()
        self.ROI.sigRegionChanged.connect(self.update_ROI)
        self.roi_pos = self.ROI.pos()
        self.roi_size = self.ROI.size()

        ## Variables for annotating images
        self.draw_rectangle = False
        self.ptRect1 = None
        self.ptRect2 = None
        self.DrawCirc = False
        self.centroid = None
        self.DrawCrossHairs = False
        self.image_offset = numpy.array([0, 0])

        self.image_label=Label("").widget
            
        self.widget=Grid(
            [self.image_label],
            [self.graphics_widget.view if self.show_LUT else self.graphics_widget],
        ).widget
        
        self.setCentralWidget(self.widget)

    def display_image(self,image,name:str=""):
        """ display image in the respective widget """
        kwargs={
            'autoLevels':False, # disable automatically scaling the image pixel values (scale so that the lowest pixel value is pure black, and the highest value if pure white)
        }
        if image.dtype==numpy.float32:
            self.graphics_widget.img.setImage(image,levels=(0.0,1.0),**kwargs)
        else:
            self.graphics_widget.img.setImage(image,**kwargs)
        self.image_label.setText(name)

    def update_ROI(self):
        self.roi_pos = self.ROI.pos()
        self.roi_size = self.ROI.size()

    def show_ROI_selector(self):
        self.ROI.show()

    def hide_ROI_selector(self):
        self.ROI.hide()

    def get_roi(self):
        return self.roi_pos,self.roi_size

    def update_bounding_box(self,pts):
        self.draw_rectangle=True
        self.ptRect1=(pts[0][0],pts[0][1])
        self.ptRect2=(pts[1][0],pts[1][1])

    def get_roi_bounding_box(self):
        self.update_ROI()
        width = self.roi_size[0]
        height = self.roi_size[1]
        xmin = max(0, self.roi_pos[0])
        ymin = max(0, self.roi_pos[1])
        return numpy.array([xmin, ymin, width, height])


class ImageArrayDisplayWindow(QMainWindow):

    def __init__(self, configuration_manager:ConfigurationManager):
        super().__init__()
        # interpret image data as row-major instead of col-major
        pg.setConfigOptions(imageAxisOrder='row-major')

        self.configuration_manager=configuration_manager

        grid_layout=Grid(with_margins=False)
        self.image_display_layout = grid_layout.layout
        self.image_display_widget = grid_layout.widget

        self.saved_images=[]
        self.set_image_displays(
            {
                11:0,
                12:1,
                14:2,
                13:3,
                15:4,

                0:6,
                1:7,
                2:8,
            },
            num_rows=3,
            num_columns=3
        )

        self.widget=VBox(
            self.image_display_widget,
            HBox(
                Checkbox("Hide BF",checked=False,on_stateChanged=lambda check_state:self.set_rows_visible([True,True,check_state!=Qt.Checked]))
            )
        ).widget

        self.setCentralWidget(self.widget)

    @TypecheckFunction
    def set_image_displays(self,channel_mappings:Dict[int,int],num_rows:int,num_columns:int,rows_enabled:Optional[List[bool]]=None):
        reverse_channel_mappings={
            value:key
            for key,value
            in channel_mappings.items()
        }

        self.num_image_displays=num_rows*num_columns
        self.channel_mappings=channel_mappings
        self.graphics_widgets=[]

        assert num_rows*num_columns>=self.num_image_displays

        # restrict zooming and moving range so that image is always in view  (part 1 of 2)
        max_state=[[-1011.6942184540692, 4011.694218454069], [-147.79939172464378, 3147.799391724644]] # furthest zoomed out
        min_state=[[1105.2084826209198, 1163.5473663736475], [1401.9018607761034, 1440.1751411998673]] # furthest zoomed in
        ((max_lowerx,max_upperx),(max_lowery,max_uppery))=max_state
        ((min_lowerx,min_upperx),(min_lowery,min_uppery))=min_state

        # create widgets and fill them with empty image display widgets
        for i in range(self.num_image_displays):
            next_graphics_widget = pg.GraphicsLayoutWidget()
            next_graphics_widget.view = next_graphics_widget.addViewBox()
            next_graphics_widget.view.setAspectLocked(True)
            next_graphics_widget.img = pg.ImageItem(border='w')
            next_graphics_widget.view.addItem(next_graphics_widget.img)

            # restrict zooming and moving (part 2 of 2)
            next_graphics_widget.view.setLimits(
                xMin=max_lowerx,
                xMax=max_upperx,
                yMin=max_lowery,
                yMax=max_uppery,

                minXRange=min_upperx-min_lowerx,
                maxXRange=max_upperx-max_lowerx,
                minYRange=min_uppery-min_lowery,
                maxYRange=max_uppery-max_lowery,
            )

            # link all views together so that each image view shows the same region
            if i>0:
                next_graphics_widget.view.setXLink(self.graphics_widgets[0][0].view)
                next_graphics_widget.view.setYLink(self.graphics_widgets[0][0].view)
            
            if i in reverse_channel_mappings:
                illumination_source_code=reverse_channel_mappings[i]

                for c in self.configuration_manager.configurations:
                    if c.illumination_source==illumination_source_code:
                        channel_name=c.name

            else:
                channel_name="<intentionally empty>"

            next_graphics_widget_wrapper=VBox(
                QLabel(channel_name),
                next_graphics_widget,
                with_margins=False,
            ).widget

            row=i//num_columns
            column=i%num_columns

            if rows_enabled is None or rows_enabled[row]:
                self.image_display_layout.addWidget(next_graphics_widget_wrapper, row, column)

                self.graphics_widgets.append((next_graphics_widget,next_graphics_widget_wrapper,row,column))

        # all views are linked, to it's enough to set the (initial) view range on a single view
        self.graphics_widgets[0][0].view.setRange(xRange=(max_lowerx,max_upperx),yRange=(max_lowery,max_uppery))
        if len(self.saved_images)==0:
            self.saved_images=[None for i in range(self.num_image_displays)]

    def display_image(self,image,channel_index:int):
        index=self.channel_mappings[channel_index]
        try:
            # display image, flipped across x (to counteract the displaying of the image as flipped across x)
            self.graphics_widgets[index][0].img.setImage(image[::-1,:],autoLevels=False)
            self.saved_images[index]=(image,channel_index)
        except IndexError:
            pass

    def set_rows_visible(self,rows_enabled:List[bool]):
        for item,wrapper,row,column in self.graphics_widgets:
            wrapper.setVisible(rows_enabled[row])


