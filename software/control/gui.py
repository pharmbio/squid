from qtpy.QtCore import Qt
from qtpy.QtWidgets import QFrame, QPushButton, QLineEdit, QDoubleSpinBox, \
    QSpinBox, QListWidget, QGridLayout, QCheckBox, QLabel, QAbstractItemView, \
    QComboBox, QHBoxLayout, QVBoxLayout, QMessageBox, QFileDialog, QProgressBar, \
    QDesktopWidget, QWidget, QTableWidget, QSizePolicy, QTableWidgetItem, \
    QApplication, QTabWidget, QStyleOption, QStyle
from qtpy.QtGui import QIcon, QPainter

from typing import Optional, Union, List, Tuple, Callable, Any

import pyqtgraph.dockarea as dock

from control.typechecker import TypecheckClass, ClosedRange, ClosedSet, TypecheckFunction

def flatten(l:list):
    ret=[]

    for item in l:
        if isinstance(item,list):
            ret.extend(item)
        else:
            ret.append(item)

    return ret

assert [2,3,4,5]==flatten([2,[3,4],5])

class ManagedObject:
    def __init__(self):
        self.value=None
    def __eq__(self,other):
        if self.value is None:
            self.value=other
            return other
        else:
            return self.value

class ObjectManager:
    def __init__(self):
        self.managed_objects={}
    def __getattr__(self,key):
        if key in self.managed_objects:
            managed_object=self.managed_objects[key]
        else:
            managed_object=ManagedObject()
            self.managed_objects[key]=managed_object

        if managed_object.value is None:
            return managed_object
        else:
            return managed_object.value

def as_widget(layout)->QWidget:
    w=QWidget()
    w.setLayout(layout)
    return w

class HasLayout():
    pass
class HasWidget():
    def __init__(self,
        enabled:Optional[bool]=None,

        **kwargs,
    ):
        if not enabled is None:
            self.widget.setEnabled(enabled)

        super().__init__(**kwargs)
        
class HasFramestyle(HasWidget):
    def __init__(self,
        frame_style:ClosedSet[Optional[str]](None,"raised","sunken")=None,

        **kwargs,
    ):
        if not frame_style is None:
            if frame_style=="raised":
                self.widget.setFrameStyle(QFrame.Panel | QFrame.Raised)
            elif frame_style=="sunken":
                self.widget.setFrameStyle(QFrame.Panel | QFrame.Sunken)

        super().__init__()

class HasToolTip(HasWidget):
    def __init__(self,
        tooltip:Optional[str]=None,

        **kwargs,
    ):
        if not tooltip is None:
            self.widget.setToolTip(tooltip)

        super().__init__(**kwargs)

class HasCallbacks(HasWidget):
    def __init__(self,**kwargs):
        unused_kwargs={}
        for key,value in kwargs.items():
            if key.startswith("on_"):
                signal_name=key[3:]
                assert len(signal_name)>0

                try:
                    if isinstance(value,list):
                        for callback in value:
                            getattr(self.widget,signal_name).connect(callback)
                    else:
                        getattr(self.widget,signal_name).connect(value)

                    # continue only if setting callback was successfull
                    continue
                except:
                    pass
            
            # if setting callback was unsuccessfull (for whatever reason), forward argument to other constructors
            unused_kwargs[key]=value

        try:
            super().__init__(**unused_kwargs)
        except TypeError as te:
            if str(te)!="object.__init__() takes exactly one argument (the instance to initialize)":
                raise te
            else:
                unused_arg_list=", ".join(unused_kwargs.keys())
                print(f"one of these arguments was unused: {unused_arg_list}")

class TextSelectable(HasWidget):
    def __init__(self,
        text_selectable:Optional[bool]=None,

        **kwargs,
    ):
        if not text_selectable is None:
            self.widget.setTextInteractionFlags(Qt.TextSelectableByMouse)

        super().__init__(**kwargs)


def try_add_member(adder,addee,*args,**kwargs):
    if isinstance(addee,HasLayout):
        try_add_member(adder,addee.layout,*args,**kwargs)
    elif isinstance(addee,HasWidget):
        try_add_member(adder,addee.widget,*args,**kwargs)
    else:
        try:
            adder.addLayout(addee,*args,**kwargs)
        except TypeError:
            adder.addWidget(addee,*args,**kwargs)

class GridItem(HasWidget):
    def __init__(self,
        widget:Optional[Any],

        row:Optional[int]=None,
        column:Optional[int]=None,
        rowSpan:Optional[int]=None,
        colSpan:Optional[int]=None,
    ):
        self.widget=widget

        self.row=row
        self.column=column
        self.rowSpan=rowSpan
        self.colSpan=colSpan

class Grid(HasLayout,HasWidget):
    def __init__(self,*args,**kwargs):
        self.layout=QGridLayout()
        row_offset=0
        for outer_index,outer_arg in enumerate(args):
            if isinstance(outer_arg,GridItem):
                if not outer_arg.widget is None:
                    try_add_member(self.layout, outer_arg.widget,
                        outer_arg.row if not outer_arg.row is None else outer_index,
                        outer_arg.column or 0,
                        outer_arg.rowSpan or 1,
                        outer_arg.colSpan or 1
                    )
                continue

            try:
                _discard=outer_arg.__iter__
                can_be_iterated_over=True
            except:
                can_be_iterated_over=False

            if can_be_iterated_over:
                col_offset=0
                for inner_index,inner_arg in enumerate(outer_arg):
                    if not inner_arg is None: # inner args can be NONE to allow for some easy padding between elements (GridItem(widget=None) achieves the same, though allows for variable padding with e.g. colSpan=2)
                        if isinstance(inner_arg,GridItem):
                            row = ( inner_arg.row if not inner_arg.row is None else outer_index ) + row_offset
                            col = ( inner_arg.column if not inner_arg.column is None else inner_index ) + col_offset
                            height = inner_arg.rowSpan or 1
                            width = inner_arg.colSpan or 1

                            if not inner_arg.widget is None:
                                try_add_member(self.layout, inner_arg.widget, row, col, height, width)

                            if width != 1:
                                col_offset+=width-1

                            continue

                        try_add_member(self.layout, inner_arg, outer_index + row_offset, inner_index + col_offset)
            else:
                try_add_member(self.layout, outer_arg, outer_index+row_offset, 0)

        super().__init__(**kwargs)

    @property
    def widget(self):
        return as_widget(self.layout)

class HBox(HasLayout,HasWidget):
    def __init__(self,*args):
        self.layout=QHBoxLayout()
        for arg in args:
            try_add_member(self.layout,arg)

    @property
    def widget(self):
        return as_widget(self.layout)

class VBox(HasLayout,HasWidget):
    def __init__(self,*args):
        self.layout=QVBoxLayout()
        for arg in args:
            try_add_member(self.layout,arg)

    @property
    def widget(self):
        return as_widget(self.layout)

class SpinBoxDouble(HasCallbacks,HasToolTip,HasWidget):
    def __init__(self,
        minimum:Optional[float]=None,
        maximum:Optional[float]=None,
        default:Optional[float]=None,
        step:Optional[float]=None,
        num_decimals=None,
        keyboard_tracking=None,
        
        **kwargs,
    ):
        self.widget=QDoubleSpinBox()

        if not minimum is None:
            self.widget.setMinimum(minimum) 
        if not maximum is None:
            self.widget.setMaximum(maximum)
        if not step is None:
            self.widget.setSingleStep(step)
        if not default is None:
            self.widget.setValue(default)
        if not num_decimals is None:
            self.widget.setDecimals(num_decimals)
        if not keyboard_tracking is None:
            self.widget.setKeyboardTracking(keyboard_tracking)

        super().__init__(**kwargs)

class SpinBoxInteger(HasCallbacks,HasToolTip,HasWidget):
    def __init__(self,
        minimum:Optional[int]=None,
        maximum:Optional[int]=None,
        default:Optional[int]=None,
        step:Optional[int]=None,
        num_decimals=None,
        keyboard_tracking=None,

        **kwargs,
    ):
        self.widget=QSpinBox()

        if not minimum is None:
            self.widget.setMinimum(minimum) 
        if not maximum is None:
            self.widget.setMaximum(maximum)
        if not step is None:
            self.widget.setSingleStep(step)
        if not default is None:
            self.widget.setValue(default)
        if not num_decimals is None:
            self.widget.setDecimals(num_decimals)
        if not keyboard_tracking is None:
            self.widget.setKeyboardTracking(keyboard_tracking)

        super().__init__(**kwargs)

class Label(TextSelectable,HasToolTip,HasWidget):
    def __init__(self,
        text:str,
        text_color:Optional[str]=None,
        background_color:Optional[str]=None,

        **kwargs,
    ):
        self.widget=QLabel(text)
        
        stylesheet=""
        if not text_color is None:
            stylesheet+=f"color : {text_color} ; "
        if not background_color is None:
            stylesheet+=f"background-color : {background_color} ; "
        if len(stylesheet)>0:
            final_stylesheet=f"QLabel {{ { stylesheet } }}"
            self.widget.setStyleSheet(final_stylesheet)

        super().__init__(**kwargs)


class Button(HasCallbacks,HasToolTip,HasWidget):
    def __init__(self,
        text:str,
        default:Optional[bool]=None,
        checkable:Optional[bool]=None,
        checked:Optional[bool]=None,

        **kwargs,
    ):
        self.widget=QPushButton(text)

        if not default is None:
            self.widget.setDefault(default)
        if not checkable is None:
            self.widget.setCheckable(checkable)
        if not checked is None:
            self.widget.setChecked(checked)

        super().__init__(**kwargs)            

class ItemList(HasCallbacks,HasToolTip,HasWidget):
    def __init__(self,
        items:List[Any],

        **kwargs,
    ):
        self.widget=QListWidget()
        self.widget.addItems(items)

        super().__init__(**kwargs)

class Dropdown(HasCallbacks,HasToolTip,HasWidget):
    def __init__(self,
        items:List[Any],
        current_index:int,

        **kwargs,
    ):
        self.widget=QComboBox()
        self.widget.addItems(items)
        self.widget.setCurrentIndex(current_index)

        super().__init__(**kwargs)
                    
class Checkbox(HasCallbacks,HasToolTip,HasWidget):
    def __init__(self,
        label:str,

        checked:Optional[bool]=None,
        
        **kwargs,
    ):
        self.widget=QCheckBox(label)

        if not checked is None:
            self.widget.setChecked(checked)

        super().__init__(**kwargs)

# special widgets

class Tab(HasWidget):
    def __init__(self,widget,title:Optional[str]=None):
        assert isinstance(widget,QWidget)
        self.widget=widget
        self.title=title

class TabBar(HasWidget):
    def __init__(self,*args):
        self.widget=QTabWidget()
        for tab in args:
            if isinstance(tab,Tab):
                self.widget.addTab(tab.widget,tab.title)
            else:
                assert isinstance(tab,QWidget)
                self.widget.addTab(tab)


class Dock(HasWidget):
    def __init__(self,widget:QWidget,title:str,minimize_height:bool=False,fixed_width:Optional[Any]=None,stretch_x:Optional[int]=100,stretch_y:Optional[int]=100):
        self.widget = dock.Dock(title, autoOrientation = False)
        self.widget.showTitleBar()
        self.widget.addWidget(widget)
        self.widget.setStretch(x=stretch_x,y=stretch_y)

        if not fixed_width is None:
            self.widget.setFixedWidth(fixed_width)

        if minimize_height:
            self.widget.setFixedHeight(self.widget.minimumSizeHint().height())

class DockArea(HasWidget):
    def __init__(self,minimize_height:bool=False,*args):
        self.widget=dock.DockArea()
        for dock in args:
            self.widget.addDock(dock)

        if minimize_height:
            self.widget.setFixedHeight(self.widget.minimumSizeHint().height())

# more like windows rather than widgets

FILTER_JSON="JSON (*.json)"

class FileDialog:
    @TypecheckFunction
    def __init__(self,
        mode:ClosedSet[str]('save','open','open_dir'),

        directory:Optional[str]=None,
        caption:Optional[str]=None,
        filter_type:Optional[str]=None,
    ):
        self.window=QFileDialog(options=QFileDialog.DontUseNativeDialog)
        self.window.setWindowModality(Qt.ApplicationModal)
        self.mode=mode

        self.kwargs={}#'options':QFileDialog.DontUseNativeDialog}
        if not directory is None:
            self.kwargs['directory']=directory
        if not caption is None:
            self.kwargs['caption']=caption
        if not filter_type is None:
            self.kwargs['filter']=filter_type
            

    def run(self):
        if self.mode=='save':
            return self.window.getSaveFileName(**self.kwargs)[0]
        elif self.mode=='open':
            return self.window.getOpenFileName(**self.kwargs)[0]
        elif self.mode=='open_dir':
            return self.window.getExistingDirectory(**self.kwargs)
        else:
            assert False

class MessageBox:
    @TypecheckFunction
    def __init__(self,
        title:str,
        mode:ClosedSet[str]('information','critical','warning','question'),

        text:Optional[str]=None,
    ):
        self.title=title
        self.mode=mode
        self.text=text

    @TypecheckFunction
    def run(self)->Optional[QMessageBox.StandardButton]:
        if self.mode=='information':
            return QMessageBox.information(None,self.title,self.text)
        elif self.mode=='critical':
            return QMessageBox.critical(None,self.title,self.text)
        elif self.mode=='warning':
            return QMessageBox.warning(None,self.title,self.text)
        elif self.mode=='question':
            question_answer:ClosedSet[int](QMessageBox.Yes,QMessageBox.No)=QMessageBox.question(None,self.title,self.text)
            return question_answer
        else:
            assert False

class BlankWidget(QWidget):
    def __init__(self,
        height:Optional[int]=None,
        width:Optional[int]=None,
        offset_left:Optional[int]=None,
        offset_top:Optional[int]=None,

        background_color:Optional[str]=None,
        background_image_path:Optional[str]=None,

        children:list=[],

        tooltip:Optional[str]=None,

        **kwargs,
    ):
        QWidget.__init__(self)

        self.background_color=background_color
        self.background_image_path=background_image_path

        self.generate_stylesheet()

        if not height is None and width is not None:
            self.resize(width,height)
        elif int(height is None) + int(width is None) == 1:
            assert False,"height and width must either both or neither be none"
        
        if not offset_left is None:
            self.move(offset_left,offset_top)
        elif int(offset_left is None) + int(offset_top is None) == 1:
            assert False,"height and width must either both or neither be none"

        self.children=[]
        self.set_children(children)

        event_handlers={}
        for key,value in kwargs.items():
            assert key[:3]=='on_'

            event_name=key[3:]
            event_handlers[event_name]=value

            if not event_name in {
                'mouseDoubleClickEvent',
                'mouseMoveEvent',
                'mousePressEvent',
                'mouseReleaseEvent',
            }:
                raise ValueError(f"event type '{event_name}' unknown")

        self.event_handlers=event_handlers

    def generate_stylesheet(self):
        stylesheet=""
        stylesheet+=f"background-color: {self.background_color or 'none'} ; "
        if not self.background_image_path is None:
            stylesheet+=f"border-image: url({self.background_image_path}) ; "
        else:
            stylesheet+=f"border-image: none ; "
        self.setStyleSheet(f" {stylesheet} ")

    def set_children(self,new_children):
        # orphan old children
        old_children=self.children
        for old_child in old_children:
            old_child.setParent(None)
            old_child.show()

        # adopt new ones
        for child in new_children:
            child.setParent(self)
            child.show()

        # replace orphans
        self.children=new_children
        self.show()

    # this needs to be done for custom QWidgets for some reason (from https://forum.qt.io/topic/100691/custom-qwidget-setstylesheet-not-working-python/2)
    def paintEvent(self, pe):
        o = QStyleOption()
        o.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, o, p, self)

    def mouseDoubleClickEvent(self,event_data):
        if 'mouseDoubleClickEvent' in self.event_handlers:
            event_handlers=self.event_handlers['mouseDoubleClickEvent']
            if isinstance(event_handlers,list):
                for callback in event_handlers:
                    callback(event_data)
            else:
                event_handlers(event_data)
    def mouseMoveEvent(self,event_data):
        if 'mouseMoveEvent' in self.event_handlers:
            event_handlers=self.event_handlers['mouseMoveEvent']
            if isinstance(event_handlers,list):
                for callback in event_handlers:
                    callback(event_data)
            else:
                event_handlers(event_data)
    def mousePressEvent(self,event_data):
        if 'mousePressEvent' in self.event_handlers:
            event_handlers=self.event_handlers['mousePressEvent']
            if isinstance(event_handlers,list):
                for callback in event_handlers:
                    callback(event_data)
            else:
                event_handlers(event_data)
    def mouseReleaseEvent(self,event_data):
        if 'mouseReleaseEvent' in self.event_handlers:
            event_handlers=self.event_handlers['mouseReleaseEvent']
            if isinstance(event_handlers,list):
                for callback in event_handlers:
                    callback(event_data)
            else:
                event_handlers(event_data)
