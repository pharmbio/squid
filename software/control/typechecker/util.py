from ast import Assert
from typing import Union, Optional, List, TypeVar, Generic, Tuple, Any, ClassVar, Callable
NoneType=type(None)
from dataclasses import Field, field, dataclass, _MISSING_TYPE
from functools import wraps
from inspect import signature, Parameter, getmro

def type_name(t)->str:
    if t is None:
        return "None"
        
    try:
        if t.__module__!="builtins":
            return f"{t.__module__}.{t.__qualname__}"
        else:
            return t.__qualname__
    except:
        return str(t)

def is_protected_symbol(symbol:str)->bool:
    return len(symbol)>4 and symbol[:2]=="__" and symbol[-2:]=="__"

class TypeCheckResult:
    def __init__(self,val:bool,msg:str=""):
        self.val=val
        self.msg=msg
    def __bool__(self)->bool:
        return self.val