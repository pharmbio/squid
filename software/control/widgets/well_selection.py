# qt libraries
from qtpy.QtCore import Qt, Signal # type: ignore
from qtpy.QtWidgets import QTableWidget, QHeaderView, QSizePolicy, QTableWidgetItem, QAbstractItemView
from qtpy.QtGui import QBrush

from control._def import *
from control.gui import *

from typing import Optional, Union, List, Tuple

from control.typechecker import TypecheckFunction
import numpy as np

class WellSelectionWidget(QTableWidget):
 
    #signal_wellSelected:Signal = Signal(int,int,float)
    signal_wellSelectedPos:Signal = Signal(float,float)

    currently_selected_well_indices:List[Tuple[int,int]]=[]

    @TypecheckFunction
    def __init__(self, gui:Any, format: int):
        self.gui=gui
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
    def set_wellplate_type(self,wellplate_type:Union[str,int]):
        if type(wellplate_type)==str:
            wellplate_type_int:int=int(wellplate_type.split(" ")[0])  # type: ignore
        else:
            wellplate_type_int:int=wellplate_type # type: ignore
 
        wellplate_type_format=WELLPLATE_FORMATS[wellplate_type_int]
        self.rows = wellplate_type_format.rows
        self.columns = wellplate_type_format.columns
        self.spacing_mm = wellplate_type_format.well_spacing_mm
 
        if self.was_initialized:
            old_layout=WELLPLATE_FORMATS[self.format]
            self.set_selectable_widgets(layout=old_layout)
 
            self.format:int=wellplate_type_int
 
            self.setRowCount(self.rows)
            self.setColumnCount(self.columns)
 
            self.setData()
        else:
            self.format=wellplate_type_int
 
            QTableWidget.__init__(self, self.rows, self.columns)
 
            self.setData()
 
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        if not self.was_initialized:
            self.setEditTriggers(QTableWidget.NoEditTriggers)
            self.cellDoubleClicked.connect(self.onDoubleClick)
 
        # size
        well_side_length=int(22*16*26/24)/self.rows # magic numbers from side_length=5*wellplate_type_format.well_spacing_mm, when using a 384 wellplate -> side length varies between plate types. use this line to set constant height (then scale by a small factor of 26/24 to make better use the horizontal space)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setMinimumSectionSize(0)
        self.verticalHeader().setDefaultSectionSize(well_side_length)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.horizontalHeader().setMinimumSectionSize(0)
        self.horizontalHeader().setDefaultSectionSize(well_side_length) # this is intentionally setMinimumSectionSize instead of setDefaultSectionSize
 
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)

        self.setFixedHeight(self.verticalHeader().length() + self.horizontalHeader().height()+2) # set fixed height because well overview widget will take up more space than it should otherwise
 
    @TypecheckFunction
    def set_selectable_widgets(self,layout:WellplateFormatPhysical):
        """ exhaustive flag means going through all items in the whole widget. otherwise, just the outer ones (on the edge) """

        # item.flags is a bitvector, so changing the IsSelectable flag is bit manipulating magic

        def set_selectable(flags:Any,selectable:bool)->Any:
            if selectable:
                return flags | Qt.ItemIsSelectable
            else:
                return flags & ~Qt.ItemIsSelectable
        
        for i in range(layout.rows):
            for j in range(layout.columns):
                item = QTableWidgetItem()
                item_is_selectable=layout.is_well_reachable(row=i,column=j,allow_corners=False)
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
            self.gui.core.navigation.move_to_index(wellplate_format,row=row,column=col)
        else:
            MessageBox(title="well inaccessible",mode="warning",text=f"The selected well at {col=}, {row=} is not accessible because of physical restrictions.").run()