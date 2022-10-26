from typing import Union, Optional, List, TypeVar, Generic, Tuple, Any
NoneType=type(None)
from dataclasses import Field
from functools import wraps
from inspect import signature, Parameter, getmro

def type_name(t)->str:
    try:
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

# compared expected to value type
# param _vt is used for recursion as part of inheritence check
def type_match(et,v,_vt=None):
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
        return TypeCheckResult(True)
    
    # check for unions, lists, tuples
    try:
        et_type_is_union=et.__origin__==Union
        et_type_is_list=et.__origin__==list
        et_type_is_tuple=et.__origin__==tuple
    except:
        et_type_is_union=False
        et_type_is_list=False
        et_type_is_tuple=False

    if et_type_is_union:
        for arg in et.__args__:
            if type_match(arg,v):
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
    return TypeCheckResult(False,msg=f"{v}:{type_name(vt)}!={type_name(et)} (generic)")

# decorator that serves as type checker for classes
def TypecheckClass(_t=None,*,check_defaults:bool=True,create_init:bool=False,create_str:bool=False):
    def inner(t):
        t_attributes={}

        sorted_keys=sorted(list(t.__dict__.keys()))

        for k,v in t.__annotations__.items():
            t_attributes[k]=v

        # check default value type match
        if check_defaults:
            for symbol in sorted_keys:
                if is_protected_symbol(symbol):
                    continue

                if callable(t.__dict__[symbol]):
                    continue

                if not symbol in t.__annotations__:
                    raise TypeError(f"no type annotation for {t.__name__}.{symbol}")

                annotated_type=t.__annotations__[symbol]
                t_attributes[symbol]=annotated_type

                try:
                    default_value=t.__dict__[symbol]
                except:
                    raise Exception("unimplemented")

                type_match_check=type_match(annotated_type,default_value)
                if not type_match_check:
                    raise TypeError(f"default value type mismatch in {t.__name__}.{symbol}: {type_match_check.msg}")

        t_attributes_sorted=sorted(list(t_attributes.keys()))

        # create __init__ method for class t
        if create_init:
            if "__init__" in t.__dict__:
                raise ValueError(f"init method already present for {t}")

            def init(s,*args,**kwargs):
                # keep track of already initialized fields to avoid overlap
                already_initialized_fields={
                    k:False
                    for k in t_attributes
                }

                def attribute_type_check_failure(a,k,type_match_check:TypeCheckResult):
                    type_a_name=type_name(type(a))
                    type_t_name=type_name(t)
                    type_k_expcted_type_name=type_name(k_expected_type)

                    raise ValueError(f"value {a}:{type_a_name} cannot be assigned to {type_t_name}.{k}:{type_k_expcted_type_name} because {type_match_check.msg}")


                # iterate over positional args to __init__
                for i,a in enumerate(args):
                    k=t_attributes_sorted[i]
                    k_expected_type=t_attributes[k]

                    type_match_check=type_match(k_expected_type,a)
                    if not type_match_check:
                        attribute_type_check_failure(a,k,type_match_check)
                    s.__dict__[k]=a
                    already_initialized_fields[k]=True

                # iterate over keyword args to __init__
                for k,a in kwargs.items():
                    if not k in t_attributes:
                        raise ValueError(f"field {k} does not exist in {t}")

                    if already_initialized_fields[k]:
                        raise ValueError(f"field {k} already initialized as positional argument")

                    k_expected_type=t_attributes[k]
                    type_match_check=type_match(k_expected_type,a)
                    if not type_match_check:
                        attribute_type_check_failure(a,k,type_match_check)

                    s.__dict__[k]=a

            t.__init__=init
        
        if create_str:
            if "__str__" in t.__dict__:
                raise ValueError(f"str method already present for {t}")

            def as_string(s)->str:
                ret=f"{t.__name__}( "
                for k,v in t_attributes.items():
                    if is_protected_symbol(k):
                        continue

                    ret+=f"{k}: {type_name(v)} = {s.__getattribute__(k)}, "

                if ret[-1]!="(":
                    ret=ret[:-2]
                
                return ret+" )"

            t.__str__=as_string

        return t

    if _t is None:
        return inner
    else:
        return inner(_t)

def TypecheckFunction(_f=None,*,check_defaults:bool=True):
    def inner(f):

        f_signature=signature(f)

        full_function_name_and_position=f"{f.__module__}.{f.__qualname__}"

        for arg_name,arg in f_signature.parameters.items():
            if arg.annotation==Parameter.empty and arg_name!="self":
                raise TypeError(f"in {full_function_name_and_position}, argument {arg_name} has no type annotation")

            if check_defaults and arg.default!=Parameter.empty:
                tmr=type_match(arg.annotation,arg.default)
                if not tmr:
                    raise TypeError(f"in {full_function_name_and_position}, argument {arg_name}:{type_name(arg.annotation)} has invalid default value {arg.default}:{type_name(type(arg.default))}")

        potentially_positional_args={arg_name:arg.annotation for arg_name,arg in f_signature.parameters.items()}

        @wraps(f)
        def wrapper(*args,**kwargs):
            for arg_i,arg in enumerate(args):
                arg_name=list(potentially_positional_args.keys())[arg_i]
                if arg_name=="self":
                    continue
                arg_expected_type=list(potentially_positional_args.values())[arg_i]

                tmr=type_match(arg_expected_type,arg)
                if not tmr:
                    raise TypeError(f"runtime argument {arg_name} at position {arg_i} in {full_function_name_and_position} has invalid type: {tmr.msg}")

            res=f(*args,**kwargs)

            if f_signature.return_annotation==Parameter.empty:
                tmr=type_match(NoneType,res)
            else:
                tmr=type_match(f_signature.return_annotation,res)

            if not tmr:
                raise TypeError(f"return value {res} mismatch in {full_function_name_and_position}: {tmr.msg}")

            return res

        return wrapper

    if _f is None:
        return inner
    else:
        return inner(_f)

T=TypeVar("T")
NO_ARG=object()
class ClosedRange(Generic[T]):
    # lower limit
    lower:T
    # upper limit
    upper:T
    # lower bound inclusive
    lb_incl:bool
    # upper bound inclusive
    ub_incl:bool

    # from https://stackoverflow.com/a/69129940
    arg:Optional[object] = NO_ARG  # using `arg` to store the current type argument
    type_arg:object

    def __class_getitem__(cls, key):
        if cls.arg is NO_ARG or cls.arg is T:
            cls.arg = key
        else:
            try:
                cls.arg = cls.arg[key] # type: ignore
            except TypeError:
                cls.arg = key
        return super().__class_getitem__(key) # type: ignore

    def __init__(self,lower:T,upper:T,lb_incl:bool=True,ub_incl:bool=True):
        self.type_arg=self.arg
        assert lower<upper # type: ignore

        tmr=type_match(self.arg,lower)
        assert tmr,f"lower bound invalid {tmr.msg}"

        tmr=type_match(self.arg,upper)
        assert tmr,f"upper bound invalid {tmr.msg}"

        self.lower=lower
        self.upper=upper

        self.lb_incl=lb_incl
        self.ub_incl=ub_incl

    def __str__(self):
        return f"ClosedRange[ {self.lower} {'<=' if self.lb_incl else '<'} {type_name(self.arg)} {'>=' if self.ub_incl else '>'} {self.upper} ]"

class ClosedSet(Generic[T]):
    valid_items:List[T]

    # from https://stackoverflow.com/a/69129940
    arg:Optional[object] = NO_ARG  # using `arg` to store the current type argument
    type_arg:object

    def __class_getitem__(cls, key):
        if cls.arg is NO_ARG or cls.arg is T:
            cls.arg = key
        else:
            try:
                cls.arg = cls.arg[key] # type: ignore
            except TypeError:
                cls.arg = key
        return super().__class_getitem__(key) # type: ignore

    def __init__(self,*args):
        self.type_arg=self.arg
        valid_items_set=set({})
        for item in args:
            assert type_match(self.arg,item)
            assert not item in valid_items_set
            valid_items_set.add(item)
        
        self.valid_items=list(valid_items_set)

    def __str__(self):
        joined_values=' | '.join(['"'+i+'"' if type(i)==str else str(i) for i in self.valid_items])
        return f"ClosedSet[ {type_name(self.arg)} : {joined_values} ]"

if __name__=="__main__":

    def test(tmr,should_fail:bool):
        if bool(tmr)==should_fail:
            raise TypeError(tmr.msg if len(tmr.msg)>0 else "should have failed, but did not")

    test( type_match(int,3), should_fail=False)
    test( type_match(int,3.0), should_fail=True) 
    test( type_match(float,3), should_fail=True) 

    test( type_match(Union[int,float],3), should_fail=False)
    test( type_match(Union[int,float],3.0), should_fail=False)
    test( type_match(Union[int,float],None), should_fail=True)
    test( type_match(Union[float,int],"hi"), should_fail=True)

    test( type_match(Optional[int],None), should_fail=False)
    test( type_match(Optional[int],3), should_fail=False)

    test( type_match(Tuple[float,int],(3.0,2)), should_fail=False)

    test( type_match(list,[3.0]), should_fail=False)
    test( type_match(List[int],[3.0]), should_fail=True)
    test( type_match(List[int],[3,3.0]), should_fail=True)
    test( type_match(List[Optional[float]],[3.0,None,2]), should_fail=True)
    test( type_match(List[Optional[float]],[3.0,None,2.0]), should_fail=False)
    test( type_match(List[Optional[float]],[]), should_fail=False)
    test( type_match(List[float],[]), should_fail=False)

    test( type_match(ClosedRange[float](1.0,2.0),1.5), should_fail=False)
    test( type_match(ClosedRange[float](1.0,2.0),1.0), should_fail=False)
    test( type_match(ClosedRange[float](1.0,2.0),2.0), should_fail=False)
    test( type_match(ClosedRange[float](1.0,2.0),3.0), should_fail=True)
    test( type_match(ClosedRange[float](1.0,2.0),3), should_fail=True)
    test( type_match(ClosedRange[float](1.0,2.0),1), should_fail=True)

    test( type_match(ClosedSet[str]("a","b"),"a"), should_fail=False)
    test( type_match(ClosedSet[str]("a","b"),"b"), should_fail=False)
    test( type_match(ClosedSet[str]("a","b"),"c"), should_fail=True)
    test( type_match(ClosedSet[str]("a","b"),1), should_fail=True)
    test( type_match(ClosedSet[int](2,3),2), should_fail=False)
    test( type_match(ClosedSet[int](2,3),3), should_fail=False)
    test( type_match(ClosedSet[int](2,3),2.0), should_fail=True)
    test( type_match(ClosedSet[int](2,3),4), should_fail=True)


    @TypecheckClass(create_str=True)
    class B:
        a:int=3
        c:float=2.0
        d:Union[float,int]=3.0
        e:List[float]=[2.0,3.0]

    @TypecheckClass(create_init=True,create_str=True)
    class C:
        a:int=3
        c:float=2.0
        d:Union[float,int]=3.0
        e:List[float]=[2.0,3.0]

        @TypecheckFunction
        def add_arg_twice_to_a(self,arg:int=2):
            self.a+=arg*2

    b=B()
    print(b)

    c=C()
    print(c)
    c=C(2,3.0,d=3,e=[3.0])
    print(c)
    c.add_arg_twice_to_a(2)
    print(c)

    @TypecheckClass(create_init=True,create_str=True)
    class TestRange:
        vt:ClosedRange[float](1.0,2.0)

    tr=TestRange(vt=1.5)
    print(tr)

    @TypecheckClass(create_init=True)
    class ParentClass:
        a:int
    @TypecheckClass(create_init=True)
    class OtherParentClass:
        a:int

    @TypecheckClass(create_init=True)
    class ChildClass(ParentClass,OtherParentClass):
        b:float

    @TypecheckFunction
    def test_inheritence_child(c:ChildClass):
        pass
    @TypecheckFunction
    def test_inheritence_base(c:ParentClass):
        pass

    test_inheritence_child(ChildClass(b=2.0))
    test_inheritence_base(ChildClass(b=2.0))

    @TypecheckClass(create_init=True,create_str=True)
    class TestSet:
        somename:ClosedSet[str]("a","b")

    tsa=TestSet(somename="a")
    print(tsa)
    tsb=TestSet(somename="b")
    print(tsb)

    @TypecheckClass(create_init=True,create_str=True)
    class TestSetStr:
        somestr:ClosedSet[str]("a","b")

    tss=TestSetStr(somestr="a")
    print(tss)

    @TypecheckClass(create_init=True,create_str=True)
    class TestSetInt:
        someint:ClosedSet[int](96,384)=96

    tsi=TestSetInt(someint=96)
    print(tsi)
