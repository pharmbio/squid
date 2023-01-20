from ast import Assert
from typing import Union, Optional, List, TypeVar, Generic, Tuple, Any, ClassVar, Callable
NoneType=type(None)
from dataclasses import Field, field, dataclass, _MISSING_TYPE
from functools import wraps
from inspect import signature, Parameter, getmro

try:
    from .util import *
except:
    from util import *

# compared expected to value type
# param _vt is used for recursion as part of inheritence check
def type_match(et,v,_vt=None):

    if isinstance(et,TypeAlias):
        return type_match(et.aliased_type,v,_vt)

    if not _vt is None:
        vt=_vt
    else:
        vt=type(v)

    # check for simple type equality
    if et==vt or et==Any:
        return TypeCheckResult(True)

    # check inheritence hierarchy
    try:
        # avoid double checking the leaf type
        inheritence_hierarchy=getmro(vt)[1:]
    except:
        inheritence_hierarchy=[]

    for cls in inheritence_hierarchy:
        if type_match(et,v,cls):
            return TypeCheckResult(True)

    # this is currently not implemented (blindly accept)
    if vt==Field:
        if type(v.default) != _MISSING_TYPE:
            tmr=type_match(et,v.default)
            if not tmr:
                return TypeCheckResult(False,f"dataclass.field(default={v.default}:{type_name(type(v.default))}) does not match {type_name(et)}")

        if type(v.default_factory) != _MISSING_TYPE:
            default_factory_generated_value=v.default_factory()
            tmr=type_match(et,default_factory_generated_value)
            if not tmr:
                return TypeCheckResult(False,f"dataclass.field(default_factory={default_factory_generated_value}:{type_name(type(default_factory_generated_value))}) does not match {type_name(et)}")

        return TypeCheckResult(True)
    
    # check for unions, lists, tuples
    try:
        et_type_is_union=et.__origin__==Union
        et_type_is_list=et.__origin__==list
        et_type_is_tuple=et.__origin__==tuple
        et_type_is_dict=et.__origin__==dict
    except:
        et_type_is_union=False
        et_type_is_list=False
        et_type_is_tuple=False
        et_type_is_dict=False

    if et_type_is_union:
        for arg in et.__args__:
            if type_match(arg,v,vt):
                return TypeCheckResult(True)

        return TypeCheckResult(False,msg=f"{v}:{type_name(vt)} not in union ({','.join([type_name(t_arg) for t_arg in et.__args__])})")
    elif et_type_is_list:
        if list!=vt:
            return TypeCheckResult(False,msg=f"{type_name(vt)} is not a list")

        for i,v in enumerate(v):
            et_list_item_type=et.__args__[0]
            if not type_match(et_list_item_type,v):
                return TypeCheckResult(False,msg=f"list item type mismatch {type_name(et_list_item_type)} != {type_name(v)} at index {i}")

        return TypeCheckResult(True)
    elif et_type_is_tuple:
        if tuple!=vt:
            return TypeCheckResult(False,msg=f"{type_name(vt)} is not a list")

        for i,v in enumerate(v):
            et_tuple_item_type=et.__args__[i]
            if not type_match(et_tuple_item_type,v):
                return TypeCheckResult(False,msg=f"tuple item type mismatch {type_name(et_tuple_item_type)} != {type_name(type(v))} at index {i}")

        return TypeCheckResult(True)
    elif et_type_is_dict:
        if dict!=vt:
            return TypeCheckResult(False,msg=f"{type_name(vt)} is not a dict")

        for k,v in v.items():
            et_dict_key_type=et.__args__[0]
            et_dict_item_type=et.__args__[1]
            if not type_match(et_dict_key_type,k):
                return TypeCheckResult(False,msg=f"dict key type mismatch {type_name(et_dict_key_type)} != {type_name(type(k))} at key {k}")
            if not type_match(et_dict_item_type,v):
                return TypeCheckResult(False,msg=f"dict item type mismatch {type_name(et_dict_item_type)} != {type_name(type(v))} at key {v}")

        return TypeCheckResult(True)

    # check for special classes: ClosedRange
    try:
        et_type_is_closed_range=et.__orig_class__.__origin__==ClosedRange
        et_type_is_closed_set=et.__orig_class__.__origin__==ClosedSet
    except:
        et_type_is_closed_range=False
        et_type_is_closed_set=False

    if et_type_is_closed_range:
        tmr=type_match(et.type_arg,v)
        if not tmr:
            return tmr

        try:
            if et.lb_incl:
                assert et.lower<=v
            else:
                assert et.lower<v
        except:
            return TypeCheckResult(False,msg="lower bound exceeded")

        try:
            if et.ub_incl:
                assert et.upper>=v
            else:
                assert et.upper>v
        except:
            return TypeCheckResult(False,msg="upper bound exceeded")

        return TypeCheckResult(True)
    elif et_type_is_closed_set:
        tmr=type_match(et.type_arg,v)
        if not tmr:
            return tmr

        for a in et.valid_items:
            if a==v:
                return TypeCheckResult(True)

        return TypeCheckResult(False,f"{et} does not contain {v}")

    # fallback to failure
    return TypeCheckResult(False,msg=f"{v}:{type_name(vt)}!={type_name(et)}")