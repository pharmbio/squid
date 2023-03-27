# qt libraries
from qtpy.QtCore import Qt, Signal, QItemSelectionModel
from qtpy.QtWidgets import QTableWidget, QHeaderView, QSizePolicy, QTableWidgetItem, QAbstractItemView
from qtpy.QtGui import QBrush

from control._def import MACHINE_CONFIG,OBJECTIVES,OBJECTIVE_NAMES,WELLPLATE_FORMATS,WELLPLATE_TYPE_IMAGE,CAMERA_PIXEL_SIZE_UM,Acquisition,WellplateFormatPhysical,WELLPLATE_NAMES
from control.gui import *

from typing import Optional, Union, List, Tuple

from control.typechecker import TypecheckFunction
import numpy as np

import pyqtgraph as pg
import cv2
from enum import Enum

class Color(tuple,Enum):
    LIGHT_BLUE=(0xAD,0xD8,0xE6)
    RED=(255,0,0)
    LIGHT_GREY=(160,)*3


class NavigationViewer(QFrame):

    def __init__(self, 
        sample:str, 
        xy_pos_changed:Signal,
        invertX:bool = False,
    ):
        super().__init__()
        self.setFrameStyle(QFrame.Panel | QFrame.Raised)

        # interpret image data as row-major instead of col-major
        pg.setConfigOptions(imageAxisOrder='row-major')
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.graphics_widget.setBackground("w")
        ## lock the aspect ratio so pixels are always square
        self.graphics_widget.view = self.graphics_widget.addViewBox(invertX=invertX,invertY=True,lockAspect=True)
        ## Create image item
        self.graphics_widget.img = pg.ImageItem(border='w')
        self.graphics_widget.view.addItem(self.graphics_widget.img)
        # make sure plate view is always visible, from view.getState()['viewRange']:
        max_state=[[-70.74301114861895, 1579.743011148619], [-254.9490586181788, 1264.9490586181787]] # furthest zoomed out
        min_state=[[733.5075292478979, 886.8248563569729], [484.2505774030056, 639.926632621451]] # furthest zoomed in
        ((max_lowerx,max_upperx),(max_lowery,max_uppery))=max_state
        ((min_lowerx,min_upperx),(min_lowery,min_uppery))=min_state
        self.graphics_widget.view.setLimits(
            #xMin=max_lowerx,
            #xMax=max_upperx,
            yMin=max_lowery,
            yMax=max_uppery,

            minXRange=min_upperx-min_lowerx,
            #maxXRange=max_upperx-max_lowerx,
            minYRange=min_uppery-min_lowery,
            maxYRange=max_uppery-max_lowery,
        )

        self.setLayout(VBox(
            self.graphics_widget,
            
            with_margins=False,
        ).layout)
 
        self.last_fov_drawn=None
 
        self.box_color = Color.RED
        self.box_line_thickness = 2
 
        self.x_mm = None
        self.y_mm = None

        self.preview_fovs=[]
        self.history_fovs=[]

        self.set_wellplate_type(sample)
        MACHINE_CONFIG.MUTABLE_STATE.objective_change.connect(lambda new_objective_str:self.set_wellplate_type(wellplate_type=self.sample))

        MACHINE_CONFIG.MUTABLE_STATE.wellplate_format_change.connect(self.set_wellplate_type)

        xy_pos_changed.connect(self.update_current_fov)

        self.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Maximum)

    def set_wellplate_type(self,wellplate_type:str):
        try:
            plate_format=WELLPLATE_FORMATS[wellplate_type]
            plate_image=WELLPLATE_TYPE_IMAGE[plate_format.num_wells]
        except:
            raise ValueError(f"{wellplate_type} is not a valid plate type")
 
        self.background_image=cv2.imread(plate_image)
 
        # current image is..
        self.current_image = np.copy(self.background_image)
        # current image display is..
        self.current_image_display = np.copy(self.background_image)
        self.image_height = self.background_image.shape[0]
        self.image_width = self.background_image.shape[1]
 
        self.sample = wellplate_type
 
        camera_pixel_size_um=CAMERA_PIXEL_SIZE_UM[MACHINE_CONFIG.CAMERA_SENSOR]
        image_width_pixels=Acquisition.CROP_WIDTH # images are square
        tube_lens_length_mm=MACHINE_CONFIG.TUBE_LENS_MM
        objective=OBJECTIVES[MACHINE_CONFIG.MUTABLE_STATE.DEFAULT_OBJECTIVE]
        objective_focal_length_mm=objective.tube_lens_f_mm/objective.magnification
        um_to_mm=1e-3
        
        WELLPLATE_IMAGE_LENGTH_IN_PIXELS=1509 # images in path(software/images) are 1509x1010
        WELLPLATE_384_LENGTH_IN_MM=127.8 # from https://www.thermofisher.com/document-connect/document-connect.html?url=https://assets.thermofisher.com/TFS-Assets%2FLSG%2Fmanuals%2Fcms_042831.pdf
        self.mm_per_pixel = WELLPLATE_384_LENGTH_IN_MM/WELLPLATE_IMAGE_LENGTH_IN_PIXELS # 0.084665 was the hardcoded value, which is closer to this number as calculated from the width of the plate at 85.5mm/1010px=0.0846535

        camera_pixel_size_in_focus_plane_mm=camera_pixel_size_um/(tube_lens_length_mm/objective_focal_length_mm)*um_to_mm # with a 20x objective, this is 1/3 um
        #print(f"info - camera pixel size in the focus plane in mm: {camera_pixel_size_in_focus_plane_mm:.6f}")
        self.fov_size_mm = image_width_pixels*camera_pixel_size_in_focus_plane_mm
        #print(f"{self.fov_size_mm=}")

        self.origin_bottom_left_x = MACHINE_CONFIG.X_ORIGIN_384_WELLPLATE_PIXEL - (MACHINE_CONFIG.X_MM_384_WELLPLATE_UPPERLEFT)/self.mm_per_pixel
        self.origin_bottom_left_y = MACHINE_CONFIG.Y_ORIGIN_384_WELLPLATE_PIXEL - (MACHINE_CONFIG.Y_MM_384_WELLPLATE_UPPERLEFT)/self.mm_per_pixel
 
        self.clear_history()
 
    @TypecheckFunction
    def coord_to_bb(self,x_mm:float,y_mm:float)->Tuple[Tuple[int,int],Tuple[int,int]]:
        topleft_x:int=round(self.origin_bottom_left_x + x_mm/self.mm_per_pixel - self.fov_size_mm/2/self.mm_per_pixel)
        topleft_y:int=round((self.origin_bottom_left_y + y_mm/self.mm_per_pixel) - self.fov_size_mm/2/self.mm_per_pixel)

        top_left = (topleft_x,topleft_y)

        bottomright_x:int=round(self.origin_bottom_left_x + x_mm/self.mm_per_pixel + self.fov_size_mm/2/self.mm_per_pixel)
        bottomright_y:int=round((self.origin_bottom_left_y + y_mm/self.mm_per_pixel) + self.fov_size_mm/2/self.mm_per_pixel)

        bottom_right = (bottomright_x,bottomright_y)

        return top_left,bottom_right

    def update_display(self):
        """
        needs to be called when self.current_image_display has been flushed
        e.g. after self.draw_current_fov() or self.clear_slide(), which is done currently
        """
        self.graphics_widget.img.setImage(self.current_image_display,autoLevels=False)

    def clear_history(self,redraw_fovs:bool=True):
        """ remove history, then redraw preview and last location """
        self.current_image = np.copy(self.background_image)
        self.current_image_display = np.copy(self.background_image)

        self.history_fovs=[]
        if redraw_fovs:
            self.redraw_fovs()

    # this is used to draw the fov when moving around live
    @TypecheckFunction
    def update_current_fov(self,x_mm:float,y_mm:float):
        self.current_image_display = np.copy(self.current_image)
        self.draw_fov(x_mm,y_mm,Color.RED)
        self.update_display()

        self.last_fov_drawn=(x_mm,y_mm)

    @TypecheckFunction
    def add_history(self,x_mm:float,y_mm:float):
        """ add to history and draw """
        self.history_fovs.append((x_mm,y_mm))
        self.draw_fov(x_mm,y_mm,Color.LIGHT_BLUE,foreground=False)
    
    # this is used to draw an arbitrary fov onto the displayed image view
    @TypecheckFunction
    def draw_fov(self,x_mm:float,y_mm:float,color:Tuple[int,int,int],foreground:bool=True):
        current_FOV_top_left, current_FOV_bottom_right=self.coord_to_bb(x_mm,y_mm)
        if foreground:
            img_target=self.current_image_display
        else:
            img_target=self.current_image
        cv2.rectangle(img_target, current_FOV_top_left, current_FOV_bottom_right, color, self.box_line_thickness)

    @TypecheckFunction
    def set_preview_list(self,preview_pos_list:List[Union[Tuple[float,float],Tuple[float,float,Tuple[int,int,int]]]]):
        self.preview_fovs=preview_pos_list
        self.redraw_fovs()

    @TypecheckFunction
    def redraw_fovs(self,history:bool=True,preview:bool=True,current:bool=True):
        self.clear_history(redraw_fovs=False)

        if preview:
            for fov in self.preview_fovs:
                if len(fov)==2:
                    self.draw_fov(x,y,Color.LIGHT_GREY,foreground=False)
                else:
                    self.draw_fov(*fov,foreground=False)

        if history:
            for x,y in self.history_fovs:
                self.draw_fov(x,y,Color.LIGHT_BLUE,foreground=False)

        if current and not self.last_fov_drawn is None:
            self.update_current_fov(*self.last_fov_drawn)


# item.flags is a bitvector, so changing the IsSelectable flag is bit manipulating magic
def set_selectable(flags:Any,selectable:bool)->Any:
    if selectable:
        return flags | Qt.ItemIsSelectable
    else:
        return flags & ~Qt.ItemIsSelectable

class WellSelectionWidget(QTableWidget):
 
    #signal_wellSelected:Signal = Signal(int,int,float)
    signal_wellSelectedPos:Signal = Signal(float,float)

    currently_selected_well_indices:List[Tuple[int,int]]=[]

    @TypecheckFunction
    def __init__(self, 
        move_to_index:Callable[[WellplateFormatPhysical,int,int],None], 
        format: str,
    ):
        self.move_to_index=move_to_index
        self.was_initialized=False
        self.set_wellplate_type(format)
        self.setSelectionMode(QAbstractItemView.MultiSelection)
        self.was_initialized=True

        self.itemSelectionChanged.connect(self.itemselectionchanged)
        MACHINE_CONFIG.MUTABLE_STATE.wellplate_format_change.connect(self.set_wellplate_type)

    def itemselectionchanged(self):
        self.currently_selected_well_indices = []

        position_index={}
        for index in self.selectedIndexes():
            row=index.row()
            column=index.column()

            if row in position_index:
                position_index[row].append(column)
            else:
                position_index[row]=[column]

        direction_left_to_right=True
        for row in sorted(position_index.keys()):
            for c in sorted(position_index[row],reverse=not direction_left_to_right):
                self.currently_selected_well_indices.append((row,c))

            direction_left_to_right=not direction_left_to_right

    @TypecheckFunction
    def widget_well_indices_as_physical_positions(self)->Tuple[List[str],List[Tuple[float,float]]]:
        # clear the previous selection
        self.coordinates_mm = []
        self.name = []
        
        # get selected wells from the widget
        if len(self.currently_selected_well_indices)>0:
            selected_wells = np.array(self.currently_selected_well_indices)
            # populate the coordinates
            rows = np.unique(selected_wells[:,0])
            _increasing = True

            for row in rows:
                items = selected_wells[selected_wells[:,0]==row]
                columns = items[:,1]
                columns = np.sort(columns)

                if _increasing==False:
                    columns = np.flip(columns)

                for column in columns:
                    well_coords=WELLPLATE_FORMATS[self.format].well_index_to_mm(int(row),int(column))
                    well_name=WELLPLATE_FORMATS[self.format].well_index_to_name(int(row),int(column))

                    self.coordinates_mm.append(well_coords)
                    self.name.append(well_name)

                _increasing = not _increasing

        return self.name,self.coordinates_mm
 
    @TypecheckFunction
    def set_wellplate_type(self,wellplate_type:str): 
        wellplate_type_format=WELLPLATE_FORMATS[wellplate_type]
        self.rows = wellplate_type_format.rows
        self.columns = wellplate_type_format.columns
 
        if self.was_initialized:
            old_layout=WELLPLATE_FORMATS[self.format]
            self.set_selectable_widgets(layout=old_layout)
 
            self.format=wellplate_type
 
            self.setRowCount(self.rows)
            self.setColumnCount(self.columns)
 
            self.setData()
        else:
            self.format=wellplate_type
 
            QTableWidget.__init__(self, self.rows, self.columns)
 
            self.setData()
 
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        if not self.was_initialized:
            self.setEditTriggers(QTableWidget.NoEditTriggers)
            self.cellDoubleClicked.connect(self.onDoubleClick)
 
        # size
        well_side_length=22*16*26/24/self.rows # magic numbers from side_length=5*wellplate_type_format.column_spacing_mm, when using a 384 wellplate -> side length varies between plate types. use this line to set constant height (then scale by a small factor of 26/24 to make better use the horizontal space)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setMinimumSectionSize(0)
        self.verticalHeader().setDefaultSectionSize(well_side_length)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.horizontalHeader().setMinimumSectionSize(0)
        self.horizontalHeader().setDefaultSectionSize(well_side_length) # this is intentionally setMinimumSectionSize instead of setDefaultSectionSize
 
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)

        self.setFixedHeight(self.verticalHeader().length() + self.horizontalHeader().height()+2) # set fixed height because well overview widget will take up more space than it should otherwise

        self.itemSelectionChanged.emit()
 
    def set_selected_wells(self,new_selection:List[Tuple[int,int]]):
        """
        deselects all currently selected wells, then selects those referenced in input list
        """

        # block signals while changing well selection (to avoid expensive recalculation triggered on every single well selection change/setCurrentCell call)
        self.blockSignals(True)

        # deselect all currently selected items
        for item_index in self.selectedIndexes():
            self.setCurrentCell(item_index.row(),item_index.column(),QItemSelectionModel.Deselect)

        # then select all items in the input selection
        for row,column in new_selection:
            # self.itemAt(row,column).setSelected(True) # this does not work for some reason?! is replaced with the setCurrentCell call below (code preserved here for a more enlightened time)
            self.setCurrentCell(row,column,QItemSelectionModel.Select)

        self.blockSignals(False)
        self.itemSelectionChanged.emit()

    @TypecheckFunction
    def set_selectable_widgets(self,layout:WellplateFormatPhysical):
        """
        dis-/allows selection of wells based on wellplate type (does not actually select wells, just allows selecting them when clicking on them)

        exhaustive flag means going through all items in the whole widget. otherwise, just the outer ones (on the edge)
        """
        
        for i in range(layout.rows):
            for j in range(layout.columns):
                item = QTableWidgetItem()
                item_is_selectable=layout.is_well_reachable(row=i,column=j)
                item_flags=set_selectable(item.flags(),selectable=item_is_selectable)
                item.setFlags(item_flags)
                if not item_is_selectable:
                    item.setBackground(QBrush(Qt.black))
                self.setItem(i,j,item)
 
    @TypecheckFunction
    def setData(self):
        # row header
        row_headers = []
        for i in range(self.rows):
            row_headers.append(chr(ord('A')+i))
        self.setVerticalHeaderLabels(row_headers)
 
        self.set_selectable_widgets(layout=WELLPLATE_FORMATS[self.format])

    @TypecheckFunction
    def onDoubleClick(self,row:int,col:int):
        wellplate_format=WELLPLATE_FORMATS[self.format]

        if wellplate_format.is_well_reachable(row=row,column=col):
            self.move_to_index(wellplate_format,row=row,column=col)
        else:
            MessageBox(title="well inaccessible",mode="warning",text=f"The selected well at {col=}, {row=} is not accessible because of physical restrictions.").run()

class WellWidget(QWidget):
    def __init__(self,
        on_move_to_index:Callable[[WellplateFormatPhysical,int,int],None],
        xy_pos_changed:Signal,
    ):
        super().__init__()

        self.interactive_widgets=ObjectManager()

        sorted_wellplate_names=[]
        # sort by number of wells, in ascending order
        for num_wells in [12,96,384]:
            # append generic version of a plate first (if none is found, dont care)
            for wellplate_name in list(WELLPLATE_NAMES):
                if wellplate_name.startswith("Generic") and wellplate_name.endswith(str(num_wells)):
                    sorted_wellplate_names.append(wellplate_name)
                    break

            # after (potentially) adding generic plate of size to list, add all others with same number of wells
            for wellplate_name in list(WELLPLATE_NAMES):
                if wellplate_name.split("-")[0]==str(num_wells):
                    sorted_wellplate_names.append(wellplate_name)
                
        self.wellplate_types=sorted_wellplate_names
        wellplate_dropdown_tooltip_str:str="Wellplate Types:\n\n"
        for wellplate_type in self.wellplate_types:
            wellplate_format=WELLPLATE_FORMATS[wellplate_type]
            wellplate_type_tooltip=wellplate_type+":"
            wellplate_type_tooltip+=f"\n\tnum wells: {wellplate_format.num_wells}"
            if len(wellplate_format.brand)>0:
                wellplate_type_tooltip+="\n\tBrand: "+wellplate_format.brand
            else:
                wellplate_type_tooltip+="\n\tBrand: <unknown>"
            wellplate_dropdown_tooltip_str+=wellplate_type_tooltip+"\n\n"

        self.objectives=OBJECTIVE_NAMES

        self.interactive_widgets.wellplate_dropdown == Dropdown(
            items=self.wellplate_types,
            current_index=self.wellplate_types.index(MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT),
            tooltip=wellplate_dropdown_tooltip_str,
            on_currentIndexChanged=self.change_wellplate_type_by_index
        ).widget
        self.interactive_widgets.objective_dropdown == Dropdown(
            items=self.objectives,
            current_index=self.objectives.index(MACHINE_CONFIG.MUTABLE_STATE.DEFAULT_OBJECTIVE),
            tooltip="Change objective to the currently installed one.\n\nActually changing the objective needs to be done manually though.\n\nThis is just for metadata and the size of the FOV in the imaging preview.",
            on_currentIndexChanged=lambda new_index:print(f"{new_index=}") or setattr(MACHINE_CONFIG.MUTABLE_STATE,"DEFAULT_OBJECTIVE",self.objectives[new_index])
        ).widget

        self.setLayout(VBox(
            self.interactive_widgets.well_selection == WellSelectionWidget(
                move_to_index = on_move_to_index,
                format = MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT,
            ),
            HBox(
                self.interactive_widgets.clear_well_selection == Button("Deselect all",tooltip="Deselects all wells in the well selection widget above.",on_clicked=lambda _btn:self.interactive_widgets.well_selection.set_selected_wells(new_selection=[])).widget,
                Label("Wellplate:").widget,
                self.interactive_widgets.wellplate_dropdown,
                Label("Objective:").widget,
                self.interactive_widgets.objective_dropdown,
            ),
            self.interactive_widgets.navigation_viewer == NavigationViewer(
                sample = MACHINE_CONFIG.MUTABLE_STATE.WELLPLATE_FORMAT,
                xy_pos_changed=xy_pos_changed,
            ),

            with_margins=False,
        ).layout)

        self.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Maximum)

    @TypecheckFunction
    def change_wellplate_type_by_index(self,new_index:int):
        new_wellplate_type=self.wellplate_types[new_index]
        self.change_wellplate_type_by_type(new_wellplate_type)

    @TypecheckFunction
    def set_objective(self,new_objective:str):
        new_objective_index=self.objectives.index(new_objective)
        if new_objective_index==-1:
            raise ValueError(f"attempted to load objective '{new_objective}' from config file. this objective is invalid.")
        self.interactive_widgets.objective_dropdown.setCurrentIndex(new_objective_index)

    @TypecheckFunction
    def change_wellplate_type_by_type(self,new_wellplate_type:str):
        self.interactive_widgets.well_selection.set_wellplate_type(new_wellplate_type)
        self.interactive_widgets.navigation_viewer.set_wellplate_type(new_wellplate_type)
        self.interactive_widgets.wellplate_dropdown.setCurrentIndex(self.wellplate_types.index(new_wellplate_type))

    @TypecheckFunction
    def get_wellplate_type(self)->str:
        return self.wellplate_types[self.interactive_widgets.wellplate_dropdown.currentIndex()]
    
    @TypecheckFunction
    def set_selected_wells(self,new_selection:List[Tuple[int,int]]):
        self.interactive_widgets.well_selection.set_selected_wells(new_selection)
    
    @TypecheckFunction
    def get_selected_wells(self)->List[Tuple[int,int]]:
        return self.interactive_widgets.well_selection.currently_selected_well_indices
    
    @TypecheckFunction
    def get_all_interactive_widgets(self)->List[QWidget]:
        return [
            self.interactive_widgets.wellplate_dropdown,
            self.interactive_widgets.objective_dropdown,
            self.interactive_widgets.well_selection,
            
            self.interactive_widgets.clear_well_selection,
        ]
    
    @TypecheckFunction
    def set_all_interactible_enabled(self,set_enabled:bool,exceptions:List[QWidget]=[]):
        for widget in self.get_all_interactive_widgets():
            if not widget in exceptions:
                widget.setEnabled(set_enabled)


    