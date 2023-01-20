"""
- dynamic typing of variables is not allowed. if a symbol of any type is already present in the current (or any parent) scope, assigning a value of any type that is incompatible with the existing type information is invalid.
"""

import ast, sys, typing, os
from pathlib import Path
import importlib

from typing import Union, List, Optional, Tuple, Any, Dict, Set

try:
    from . import util
    from .util import TypeCheckResult, TypeAlias
except:
    import util
    from util import TypeCheckResult, TypeAlias

def type_name(t)->str:
    if isinstance(t,ClassChecker):
        return t.scope.full_name

    return util.type_name(t)

def op_name(op)->str:
    if isinstance(op,ast.Add):
        return "add"
    elif isinstance(op,ast.Sub):
        return "sub"
    elif isinstance(op,ast.Mult):
        return "mult"
    elif isinstance(op,ast.Div):
        return "div"
    elif isinstance(op,ast.FloorDiv):
        return "floordiv"

def private(cls):
    """ this is just used as decorator for a scope that contains private symbols """
    return cls
def annotation_block(b):
    """ because of how python decorators work, a class containing module annotations can be wrapped in this"""
    pass

class FunctionHeader:
    def __init__(self,
        name:str,

        return_type:type=None,

        posonlyargs:List[Tuple[str,type]]=[],
        args:List[Tuple[str,type]]=[],
        kwonlyargs:List[Tuple[str,type]]=[],

        args_with_default_values:Dict[str,bool]={},

        starargs:bool=False,
        starkwargs:bool=False,

        scope:Optional[Any]=None,
    ):
        self.name=name
        self.return_type=return_type

        self.posonlyargs=posonlyargs
        self.args=args
        self.kwonlyargs=kwonlyargs

        self.starargs=starargs
        self.starkwargs=starkwargs

        self.args_with_default_values=args_with_default_values

        self.scope=scope

    def get_args(self):
        return [
            *self.posonlyargs,
            *self.get_kwargs(),
        ]

    def get_kwargs(self)->dict:
        return [
            *self.args,
            *self.kwonlyargs,
        ]

class TypeCheckError(Exception):
    def __init__(self,node=None):
        super().__init__()
        self.node=node
    def __str__(self):
        return "some typechecking error. you should not see this."

class TypesUnequal(TypeCheckError):
    def __init__(self,node,expected_type,got_type):
        super().__init__(node=node)
        self.expected_type=expected_type
        self.got_type=got_type
    def __str__(self):
        return f"expected type {type_name(self.expected_type)}, got {type_name(self.got_type)} instead"
class IncompatibleBinOpTypes(TypeCheckError):
    def __init__(self,node,left_type,right_type,op):
        super().__init__(node=node)
        self.left_type=left_type
        self.right_type=right_type
        self.op=op
    def __str__(self):
        return f"incompatible types {type_name(self.left_type)} and {type_name(self.right_type)} for op {op_name(self.op)}"
class ValueCannotBeNone(TypeCheckError):
    def __init__(self,node):
        super().__init__(node=node)
    def __str__(self):
        return f"value cannot have type None."
class UnknownSymbol(TypeCheckError):
    def __init__(self,symbol_name:str,**kwargs):
        super().__init__(**kwargs)
        self.symbol_name=symbol_name
    def __str__(self):
        return f"unknown symbol '{self.symbol_name}'"
class UnusedArgument(TypeCheckError):
    def __init__(self,symbol_name:str,**kwargs):
        super().__init__(**kwargs)
        self.symbol_name=symbol_name
    def __str__(self):
        return f"unused argument '{self.symbol_name}'"
class ArgumentNumberMismatch(TypeCheckError):
    def __init__(self,expect_num:int,got_num:int,node):
        super().__init__(node=node)
        self.expect_num=expect_num
        self.got_num=got_num
    def __str__(self)->str:
        return f"expected {self.expect_num} arguments, got {self.got_num} instead."

class FunctionArgumentMissing(TypeCheckError):
    def __init__(self,func,arg,site):
        super().__init__(node=site)
        self.arg=arg
    def __str__(self):
        return f"missing argument '{self.arg}'"

class BreakOutsideLoop(TypeCheckError):
    def __init__(self,node):
        super().__init__(node=node)
    def __str__(self):
        return "break not allowed outside of a loop"
class ContinueOutsideLoop(TypeCheckError):
    def __init__(self,node):
        super().__init__(node=node)
    def __str__(self):
        return "continue not allowed outside of a loop"
class CannotReturnHere(TypeCheckError):
    def __init__(self,node):
        super().__init__(node=node)
    def __str__(self):
        return "cannot return from here"
class SymbolAlreadyExists(TypeCheckError):
    def __init__(self,new_node,old_node:Optional[Any]=None):
        super().__init__(node=new_node)
        self.new_node=new_node
        self.old_node=old_node
    def __str__(self):
        if isinstance(self.new_node,ast.ClassDef):
            node_name=self.new_node.name
        else:
            node_name=self.new_node.id

        if self.old_node is None:
            return f"{node_name} already exists"
        else:
            return f"{node_name} already exists, previous definition in line {self.old_node.lineno}"
class MissingReturn(TypeCheckError):
    def __init__(self,node):
        super().__init__(node=node)
    def __str__(self):
        return "current scope must return a value"
class ExpectedType(TypeCheckError):
    def __init__(Self,node):
        super().__init__(node=node)
    def __str__(self):
        return "expected a type, got something else instead"
class CannotDiscardValueImplicitely(TypeCheckError):
    def __init__(self,statement,expression_type):
        super().__init__(node=statement)
        self.expression_type=expression_type
    def __str__(self):
        return f"cannot discard value of type {type_name(self.expression_type)} implicitely."

class UnknownAttribute(TypeCheckError):
    def __init__(self,node,container_type:type):
        super().__init__(node=node)
        self.container_type=container_type
    def __str__(self):
        try:
            node_name=type_name(self.node.name)
        except:
            node_name=type_name(self.node)

        return f"type {type_name(self.container_type)} does not have attribute {self.node.attr}"
class MissingTypeAnnotation(TypeCheckError):
    def __init__(self,node):
        super().__init__(node=node)
    def __str__(self):
        return "missing type annotation."
class AnnotationForUnknownModule(TypeCheckError):
    def __init__(self,module_name:str,node):
        super().__init__(node=node)
        self.module_name=module_name
    def __str__(self):
        return f"provided annotation for unknown (not yet imported?) module: {self.module_name} ."

try:
    from .type_match import type_match
except:
    from type_match import type_match

def typecheck_assignment(node,left_type,right_type)->TypeCheckResult:
    if type_match(left_type,None,right_type):
        return TypeCheckResult(True)

    raise TypesUnequal(node,left_type,right_type)

def bin_op_result_type(left_type,right_type,op,strict_type_compatiblity:bool=False)->Optional[type]:
    valid_types=(bool,int,float) # bool and int are treated very similarly in python

    assert left_type in valid_types,f"left type is {left_type}"
    assert right_type in valid_types,f"right type is {right_type}"

    # ops promoting to the higher type, e.g. int op float -> float, but int op int -> int
    if isinstance(op,(
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
    )):
        if left_type==right_type:
            return left_type
        else:
            if strict_type_compatiblity:
                return None

            if left_type == float or right_type==float:
                return float

            assert False, "unreachable"
    # ops always promoting to float
    elif isinstance(op,(
        ast.Div,
    )):
        if strict_type_compatiblity:
            return None

        if left_type in (int,float):
            return float
        
        assert False, f"unreachable {left_type}"
    # ops only valid for integers
    elif isinstance(op,(
        ast.LShift,
        ast.RShift,
        ast.BitOr,
        ast.BitXor,
        ast.BitAnd,
    )):
        if not left_type == float:
            return int
        
        assert False, "unreachable"

    return None

class Scope:
    def __init__(self,
        parent=None,
        can_return:bool=False,
        must_return:bool=False,
        return_type:Optional[type]=None,
        in_loop:bool=False,
        location:Optional[str]=None,
        known_symbol_types:Optional[dict]=None,
        name:Optional[str]=None,

        code_str:Optional[str]=None,
        is_class:bool=False,
    ):
        self.parent=parent
        self.known_symbol_types=known_symbol_types or {}
        self.can_return=can_return
        self.must_return=must_return
        self.return_type=return_type
        self.in_loop=in_loop
        self.location=location
        self.name=name

        if self.parent is None:
            assert not code_str is None, "the topmost scope must have the source code attached"
            self.code_str=code_str
        else:
            assert code_str is None, "only the topmost scope must have the source code attached"
            self.code_str=self.parent.code_str

        self.is_class=is_class

    @property
    def full_name(self)->str:
        self_name=(self.name or "")
        ret=""
        if not self.parent is None:
            if len(self.parent.full_name)>0:
                ret=self.parent.full_name
        if len(self_name)>0:
            if len(ret)>0:
                ret+="."+self_name
            else:
                ret=self_name

        return ret

    @property
    def full_location(self)->str:
        if self.parent is None:
            parent_location=""
        else:
            parent_location=self.parent.full_location+" "

        if not self.location is None:
            return parent_location+"in "+self.location
        else:
            return parent_location

    def highlighted_error_location(self,node)->str:
        if node is None:
            return self.full_location

        statement_code_location=f"  line {node.lineno} : "
        
        statement_code_text=self.code_str.splitlines()[node.lineno-1]

        code_highlight=(" "*(len(statement_code_location)+node.col_offset))+("^"*(node.end_col_offset-node.col_offset))

        return f"{self.full_location}\n{statement_code_location}{statement_code_text}\n{code_highlight}"

    def resolve_symbol_name_to_type(self,symbol:Union[str,ast.Name])->type:
        """ resolve symbol _name_ to a type (only applicable to alone standing symbol names) """

        if isinstance(symbol,str):
            name=symbol
        elif isinstance(symbol,ast.Name):
            name=symbol.id
        else:
            assert False, f"unreachable {symbol}"

        if name in self.known_symbol_types:
            symbol_type=self.known_symbol_types[name]
            return symbol_type
        else:
            if not self.parent is None:
                return self.parent.resolve_symbol_name_to_type(symbol)

            raise UnknownSymbol(name,node=symbol)

    def eval_value_type(self,value)->type:
        if isinstance(value,ast.Constant):
            return type(value.value)

        elif isinstance(value,(ast.Name,str)):
            if isinstance(value,str):
                name=value
            else:
                name=value.id

            try:
                return self.resolve_symbol_name_to_type(value)
            except UnknownSymbol:
                pass

            if name in BUILTIN_FUNCTION_ANNOTATIONS:
                return BUILTIN_FUNCTION_ANNOTATIONS[name]
            elif name in __builtins__.__dict__.keys():
                assert False, f"did not implement anntations for builtin function {name}"
            else:
                if not self.parent is None:
                    return self.parent.eval_value_type(value)

                raise UnknownSymbol(name,node=value)

        elif isinstance(value,ast.BinOp):
            return bin_op_result_type(
                left_type=self.eval_value_type(value.left),
                right_type=self.eval_value_type(value.right),
                op=value.op
            )
            
        elif isinstance(value,ast.Call):
            func_type=self.eval_value_type(value.func)

            try:
                starargs=value.starargs
            except:
                starargs=None
            try:
                kwargs=value.kwargs
            except:
                kwargs=None

            return self.validate_function_call(
                called_node=func_type,
                args=value.args,
                keywords=value.keywords,
                starargs=starargs,
                kwargs=kwargs,
                call_node=value
            )

        elif isinstance(value,ast.Tuple):
            assert False, "tuple values currently unimplemented"

        elif value is None:
            # not suuuuuper correct, but allows specifying None as function return type instead of NoneType (which would be the 'correct' behaviour, but seems unintuitive)
            return None

        elif isinstance(value,ast.Attribute):
            container_type=self.eval_value_type(value.value)

            if isinstance(container_type,type): # for builtin types
                if value.attr in container_type.__dict__:
                    builtin_function=container_type.__dict__[value.attr]
                    if builtin_function in BUILTIN_FUNCTION_ANNOTATIONS:
                        return BUILTIN_FUNCTION_ANNOTATIONS[builtin_function]

                    return type(builtin_function)

                raise UnknownAttribute(node=value,container_type=container_type)
            elif isinstance(container_type,ClassChecker):
                class_type=container_type
                try:
                    return class_type.scope.resolve_symbol_name_to_type(value.attr)
                except UnknownSymbol:
                    pass

                raise UnknownAttribute(node=value,container_type=container_type)

            # container is module annotation
            elif isinstance(container_type,Module):
                return container_type.scope.eval_value_type(value.attr)

        elif isinstance(value,ast.FormattedValue):
            value_type=self.eval_value_type(value.value) # check value type to ensure the value exists

            if value.conversion==-1: # no (default?) conversion
                return str
            elif value.conversion==115: # str conversion
                return str
            elif value.conversion==114: # repr conversion
                return str
            elif value.conversion==97: # print("ascii conversion")
                return str
            else:
                assert False, f"unknown conversion specifier {value.conversion}"

            # TODO currently value.format_spec is ignored. unsure if this can effect the formatting value type somehow

        elif isinstance(value,ast.JoinedStr):
            for segment in value.values:
                segment_value_type=self.eval_value_type(segment)
                if not segment_value_type==str:
                    raise TypesUnequal(left_type=str,right_type=segment_value_type,node=value)

            return str

        else:
            try:
                type_type=self.type_annotation_to_type(value)
                return TypeAlias(aliased_type=type_type)
            except Exception as e:
                raise e
        
        assert False,f"unknown type {ast.dump(value)}"
    
    def type_annotation_to_type(self,type_annotation:Union[ast.Name,ast.Constant,ast.Subscript],replace_none_with_type:bool=False,node:Optional[Any]=None)->type:
        if type_annotation is None:
            if replace_none_with_type:
                type_annotation=AST_TYPE_ANNOTATIONS[None]
            else:
                raise MissingTypeAnnotation(node=node)

        if isinstance(type_annotation,ast.Name):
            if type_annotation.id in BUILTIN_TYPE_NAMES:
                return BUILTIN_TYPE_NAMES[type_annotation.id]
            elif type_annotation.id in self.known_symbol_types:
                return self.known_symbol_types[type_annotation.id]
            elif not self.parent is None:
                return self.parent.type_annotation_to_type(type_annotation)
            
            raise UnknownSymbol(type_annotation.id,node=type_annotation)

        elif isinstance(type_annotation,ast.Attribute):
            return self.eval_value_type(type_annotation)

        elif isinstance(type_annotation,ast.Constant):
            if type_annotation.value is None:
                return None
            
            raise ExpectedType(node=type_annotation)

        elif isinstance(type_annotation,ast.Subscript):
            if isinstance(type_annotation.value,ast.Name):
                if type_annotation.value.id=="Optional":
                    if isinstance(type_annotation.slice,ast.Name):
                        inner_type=self.type_annotation_to_type(type_annotation.slice)
                        
                        return Optional[inner_type]
                    else:
                        assert False, f"unreachable: {type_annotation.slice}"
                elif type_annotation.value.id=="Union":
                    inner_types=tuple([
                        self.type_annotation_to_type(element)
                        for element
                        in type_annotation.slice.value.elts
                    ])
                    
                    t=typing._GenericAlias(typing.Union,inner_types)

                    assert typecheck_assignment(None,typing._GenericAlias(typing.Union,(int,float)),int)

                    return t
                else:
                    assert False, f"unreachable: {type_annotation.value.id}"
            else:
                assert False, f"unreachable: {type_annotation.value}"

        else:
            assert False,f"could not resolve type annotation {ast.dump(type_annotation)}"

    def validate_function_call(self, 
        called_node, # currently implemented as FunctionChecker
        args:list, # meaning arguments passed as positional arguments
        keywords:List[ast.keyword], # meaning arguments passed by keyword
        starargs:Optional[Any], # meaning *args
        kwargs:Optional[Any], # meaning **kwargs

        call_node:ast.Call,
    )->type:
        # set up structure to keep track of arguments provided in the function call
        if isinstance(called_node,FunctionChecker):
            func_type=called_node
            return_type=func_type.scope.return_type
            func_args=func_type.get_args()
        elif isinstance(called_node,ClassChecker):
            if not CONSTRUCTOR_NAME in called_node.scope.known_symbol_types:
                raise UnknownSymbol(CONSTRUCTOR_NAME,node=call_node)

            func_type=called_node.scope.known_symbol_types[CONSTRUCTOR_NAME]
            return_type=called_node
            func_args=func_type.get_args()
        elif isinstance(called_node,ast.Name):
            assert False, "unreachable"
        elif isinstance(called_node,FunctionHeader):
            func_type=called_node
            return_type=func_type.return_type
            func_args=func_type.get_args()
        else:
            assert False, f"unreachable. calling node other than function/class: {called_node}"

        args_accounted_for={arg[0]:False for arg in func_args}

        # check positional arguments first. (validate types and keep track of which ones were provided)
        if len(args)>len(func_args):
            raise ArgumentNumberMismatch(expect_num=len(func_args),got_num=len(args),node=call_node)

        for pos,pos_arg in enumerate(args):
            arg_name,arg_type=func_args[pos]
            left_type=arg_type

            right_type=self.eval_value_type(pos_arg)
            typecheck_assignment(pos_arg,left_type,right_type)

            args_accounted_for[arg_name]=True

        # check arguments passed by keyword. (validate types and keep track of which ones were provided)
        func_kw_args=func_type.get_kwargs()
        unused_kwargs={}
        for kw in keywords:
            if not kw.arg in func_kw_args:
                unused_kwargs[kw.arg]=kw
                continue

            func_arg_type=func_kw_args[kw.arg]
            left_type=func_arg_type

            right_type=self.eval_value_type(kw.value)

            typecheck_assignment(kw,left_type,right_type)

            args_accounted_for[kw.arg]=True
            
        # *args
        if not starargs is None and len(starargs)>0:
            assert False, "unimplemented"
        # **kwargs
        for name,kw_arg in unused_kwargs.items():
            raise UnusedArgument(name,node=kw_arg)

        if not kwargs is None and len(kwargs)>0:
            assert False, "unimplemented"

        # make sure that all function arguments have been provided (TODO currently does not take default argument values into account)
        for arg,accounted_for in args_accounted_for.items():
            if not accounted_for and not ( \
                (func_type.scope.parent.is_class and arg == "self") \
                or arg in func_type.args_with_default_values
            ):
                raise FunctionArgumentMissing(func=func_type,arg=arg,site=call_node)

        return return_type


    def validate_statements(self,nodes,allow_docstring:bool=False,verify_annotation_accuracy:bool=True):
        remaining_nodes=nodes
        try:
            if allow_docstring and len(nodes)>=1:
                try:
                    first_node_type=self.validate_statement(nodes[0])
                except CannotDiscardValueImplicitely as c:
                    if c.node!=nodes[0]:
                        raise c

                remaining_nodes=nodes[1:]

            for node in remaining_nodes:
                self.validate_statement(node,verify_annotation_accuracy=verify_annotation_accuracy)

            if len(remaining_nodes)>=1 and verify_annotation_accuracy:
                if self.can_return and (not self.return_type is None) and self.must_return and not isinstance(remaining_nodes[-1],ast.Return):
                    raise MissingReturn(node)

        except TypeCheckError as t:
            raise ValueError(self.highlighted_error_location(t.node)+"\n"+str(t))

    def validate_statement(self,statement,verify_annotation_accuracy:bool=True):
        if isinstance(statement,ast.Return):
            """ e.g. return 3; or return a """
            if not self.can_return:
                raise CannotReturnHere(node=statement)

            return_value=statement.value

            right_type=self.eval_value_type(return_value)
            res=typecheck_assignment(statement,left_type=self.return_type,right_type=right_type)

        elif isinstance(statement,ast.Pass):
            pass # the pass statement, which does not actually 'do' anything

        elif isinstance(statement,ast.Assign):
            """ e.g. a=3; or b=1 """ # note that type annotations are missing here
            assignment=statement

            right_type=self.eval_value_type(assignment.value)

            for target in assignment.targets:
                try:
                    left_type=self.eval_value_type(target)
                    new_symbol_inserted=False
                except UnknownSymbol as u:
                    new_symbol_inserted=True
                    self.known_symbol_types[u.symbol_name]=right_type

                if not new_symbol_inserted:
                    res=typecheck_assignment(assignment,left_type,right_type)

        elif isinstance(statement,ast.AugAssign):
            """ e.g. a/=3; or b+=1 """
            left_type=self.resolve_symbol_name_to_type(statement.target)
            right_type=self.eval_value_type(statement.value)

            # if left type is float, type on right side does not matter (as long as it is a valid arithmetic type), the result will be float
            strict_type_compatiblity=left_type!=float

            if not bin_op_result_type(left_type,right_type,op=statement.op,strict_type_compatiblity=strict_type_compatiblity)==left_type:
                raise IncompatibleBinOpTypes(node=statement,left_type=left_type,right_type=right_type,op=statement.op)

        elif isinstance(statement,ast.If):
            """ includes if[/else], and if/elif[/else]"""
            if_value_type=self.eval_value_type(statement.test)

            Scope(parent=self,in_loop=False,can_return=self.can_return,return_type=self.return_type).validate_statements(statement.body)
            Scope(parent=self,in_loop=False,can_return=self.can_return,return_type=self.return_type).validate_statements(statement.orelse)

        elif isinstance(statement,ast.While):
            """ while loop """
            while_value_type=self.eval_value_type(statement.test)

            Scope(parent=self,in_loop=True,can_return=self.can_return,return_type=self.return_type).validate_statements(statement.body)

        elif isinstance(statement,ast.Break):
            """ break statement only valid inside a loop """
            if not self.in_loop:
                raise BreakOutsideLoop(node=statement)

        elif isinstance(statement,ast.Continue):
            """ continue statement only valid inside a loop """
            if not self.in_loop:
                raise ContinueOutsideLoop(node=statement)

        elif isinstance(statement,ast.Import):
            """ e.g. import math; or impart math as m """
            for module in statement.names:
                module_name=module.name

                print(importlib.util.find_spec("util"))

                if module_name=="typechecker":
                    pass
                else:
                    pass

                if module_name in self.known_symbol_types:
                    raise SymbolAlreadyExists(new_node=statement)

                print(f"imported module {module_name}")
                self.known_symbol_types[module_name]=Module(real_name=module_name,alias_name=module_name,scope=Scope(parent=self))
            
            #raise Exception(f"importing modules is not supported (importing module(s) '{','.join([i.name for i in statement.names])}' here)")

        elif isinstance(statement,ast.FunctionDef):
            if self.is_class:
                if len(statement.args.args)>=1:
                    first_arg=statement.args.args[0]
                    if first_arg.arg=="self" and first_arg.annotation is None:
                        first_arg.annotation=ast.Name(id="Self",ctx=ast.Load())

            function=FunctionChecker(self,statement)

            function_name=function.function.name

            if function_name in self.known_symbol_types:
                # create fake function name node to be compatible with SymbolAlreadyExists
                fake_function_name_node=ast.Name(
                    id=function_name,ctx=ast.Store(),
                    lineno=statement.lineno,end_lineno=statement.lineno,
                    col_offset=statement.col_offset+4,end_col_offset=statement.col_offset+4+len(function_name)
                )
                raise SymbolAlreadyExists(new_node=fake_function_name_node,old_node=self.known_symbol_types[function_name].function)
                
            self.known_symbol_types[function_name]=function

        elif isinstance(statement,ast.AnnAssign):
            """ e.g. a:int=3; or a:int """ # note the optional right-side value (if no value is given on the right side of the assignment, the python runtime will not assign any value to the variable, i.e. effectively ignore the annotation statement)
            assert statement.simple, f"complex annassign not suppported currently"
            assert isinstance(statement.target,ast.Name)
            symbol_name=statement.target.id
            # resolve type
            symbol_type=self.type_annotation_to_type(statement.annotation)

            # check if symbol exists already
            if symbol_name in self.known_symbol_types:
                raise SymbolAlreadyExists(new_node=statement)

            self.known_symbol_types[symbol_name]=symbol_type

            if not statement.value is None:
                # check if value type is valid
                value_type=self.eval_value_type(statement.value)

                typecheck_assignment(node=statement,left_type=symbol_type,right_type=value_type)

        elif isinstance(statement,ast.Expr):
            """ expression that evaluates to some type. if the type it evaluates to is not None (i.e. no type/value), raise exception. """
            expression_type=self.eval_value_type(statement.value)

            if not expression_type is None:
                raise CannotDiscardValueImplicitely(statement,expression_type)

        elif isinstance(statement,ast.ClassDef):
            class_name=statement.name

            for decorator in statement.decorator_list:
                decorator_name=""
                inner_decorator=decorator
                while True:
                    if isinstance(inner_decorator,ast.Name):
                        decorator_name=inner_decorator.id+decorator_name
                        break
                    elif isinstance(inner_decorator,ast.Attribute):
                        decorator_name="."+inner_decorator.attr+decorator_name
                        inner_decorator=inner_decorator.value
                    else:
                        assert False, str(inner_decorator)

                if decorator_name=="tc.module_checker.annotation_block" or decorator_name=="typechecker.module_checker.annotation_block":
                    for statement in statement.body:
                        if isinstance(statement,ast.ClassDef):
                            class_name=statement.name

                            if not class_name in self.known_symbol_types:
                                raise AnnotationForUnknownModule(class_name,node=statement)

                            module=self.known_symbol_types[class_name]
                            module.scope.validate_statements(statement.body,verify_annotation_accuracy=False)
                        else:
                            assert False, f"statement is not classdef, is instead: {statement}"

                    return

                print(f"found decorator {decorator_name} for classdef")

            for base_class in statement.bases:
                print(f"found base class {base_class} for class {class_name}")
            for kwarg in statement.keywords:
                print(f"found keyword arguments for class definition: {kwarg}")

            try:
                print(f"starargs exists: {statement.starargs}")
            except:
                pass

            try:
                print(f"kwargs exist: {statement.kwargs}")
            except:
                pass

            if class_name in self.known_symbol_types:
                raise SymbolAlreadyExists(new_node=statement)

            class_scope=Scope(parent=self)
            class_checker_object=ClassChecker(statement,class_scope)

            self.known_symbol_types[class_name]=class_checker_object


            class_scope.validate_statements(statement.body,allow_docstring=True)

        else:
            assert False, f"unimplemented {statement}"

class Module:
    """ module annotation """
    real_name:str
    alias_name:str
    scope:Scope
    def __init__(self,real_name:str,alias_name:str,scope:Scope):
        self.real_name=real_name
        self.alias_name=alias_name
        self.scope=scope
        self.scope.name=self.alias_name

class ClassChecker:
    def __init__(self,class_def_node,class_scope):
        self.node=class_def_node
        self.scope=class_scope
        self.scope.name=self.node.name

        assert not self.scope.is_class
        self.scope.is_class=True

        self.scope.known_symbol_types["Self"]=self

class FunctionChecker:
    def __init__(self,parent_module,function):
        self.parent_scope=parent_module

        self.function=function
        self.name=self.function.name

        self.scope=Scope(self.parent_scope,can_return=True,must_return=True,in_loop=False,location=f"function '{self.function.name}'")
        self.scope.return_type=self.scope.type_annotation_to_type(function.returns,replace_none_with_type=True,node=function)

        self.arguments=[]

        # handle function.args.{vararg is *arg, kwarg is **kwargs}
        for arg in function.args.posonlyargs:
            arg_type=self.scope.type_annotation_to_type(arg.annotation,node=arg)
            self.scope.known_symbol_types[arg.arg]=arg_type

        for arg in function.args.args:
            arg_type=self.scope.type_annotation_to_type(arg.annotation,node=arg)
            if arg_type is None:
                assert False, f"resolving type_annotation returned None? in FunctionChecker.__init__(): {ast.dump(function)}"
            self.scope.known_symbol_types[arg.arg]=arg_type

        for arg in function.args.kwonlyargs:
            arg_type=self.scope.type_annotation_to_type(arg.annotation,node=arg)
            self.scope.known_symbol_types[arg.arg]=arg_type

        self.scope.validate_statements(function.body,allow_docstring=True)

        self.args_with_default_values=set({})
        if len(function.args.posonlyargs)>0:
            assert len(function.args.posonlyargs)==len(function.args.defaults)

        for pos_index,pos_default in enumerate(function.args.defaults):
            if not pos_default is None:
                pos_arg_index=-len(function.args.defaults)+pos_index
                referenced_arg=self.function.args.args[pos_arg_index]

                default_value_type=self.scope.eval_value_type(pos_default)
                typecheck_assignment(pos_default,self.scope.known_symbol_types[referenced_arg.arg],default_value_type)

                self.args_with_default_values.add(referenced_arg.arg)
        for kw_index,kw_default in enumerate(function.args.kw_defaults):
            if not kw_default is None:
                self.args_with_default_values.add(self.function.args.kwonlyargs[kw_index].arg)

    def get_args(self)->list:
        return [
            *[
                (arg.arg,self.scope.resolve_symbol_name_to_type(arg.arg))
                for arg
                in self.function.args.posonlyargs
            ],
            *[
                (name,value_type)
                for (name,value_type)
                in self.get_kwargs().items()
            ],
        ]

    def get_kwargs(self)->dict:
        kwargs={}
        kwargs.update({
            arg.arg:self.scope.resolve_symbol_name_to_type(arg.arg)
            for arg
            in self.function.args.args
        })
        kwargs.update({
            arg.arg:self.scope.resolve_symbol_name_to_type(arg.arg)
            for arg
            in self.function.args.kwonlyargs
        })
        return kwargs

    @property
    def filename(self):
        return self.parent_module.filename
    @property
    def file_contents(self):
        return self.parent_module.file_contents

class ModuleChecker:
    def __init__(self,filename:str,print_ast:bool=False):
        self.filename=filename

        with open(filename,"r",encoding="utf8") as target_file:
            self.file_contents=target_file.read()

        self.scope=Scope(location=self.filename,code_str=self.file_contents)

        target_ast=ast.parse(self.file_contents,filename=filename) # provide filename for parsing error messages

        if print_ast:
            print(ast.dump(target_ast))

        self.scope.validate_statements(target_ast.body)


CONSTRUCTOR_NAME="__init__"
BUILTIN_TYPE_NAMES={
    'None':None,

    'str':str,
    'bool':bool,
    'int':int,
    'float':float,
}
AST_TYPE_ANNOTATIONS={
    str:ast.Name(id="str",ctx=ast.Load()),
    None:ast.Name(id="None",ctx=ast.Load()),
}
BUILTIN_CLASS_SCOPES={
    str:Scope(
        parent=None,
        is_class=True,
        code_str="",
    )
}
BUILTIN_FUNCTION_ANNOTATIONS={
    "print":FunctionHeader(
        name="print",
        return_type=str,
        args=[
            ("item",str)
        ],
        kwonlyargs=[
            ("sep",str),
        ],
        args_with_default_values={"sep"}
    ),
    "int":FunctionHeader(
        name="int",
        return_type=int,
        posonlyargs=[('val',float)],
    ),
    "float":FunctionHeader(
        name="float",
        return_type=float,
        posonlyargs=[('val',int)],
    ),

    str.startswith:FunctionHeader(
        name="startswith",
        args=[('start_sym',str)],
        return_type=bool,
        scope=Scope(parent=BUILTIN_CLASS_SCOPES[str]),
    ),
    str.endswith:FunctionHeader(
        name="endswith",
        args=[('end_sym',str)],
        return_type=bool,
        scope=Scope(parent=BUILTIN_CLASS_SCOPES[str]),
    ),
    str.split:FunctionHeader(
        name="split",
        args=[("sep",str),("maxsplit",int)],
        args_with_default_values={"sep","maxsplit"},
        return_type=bool,
        scope=Scope(parent=BUILTIN_CLASS_SCOPES[str]),
    ),
    str.lower:FunctionHeader(
        name="lower",
        return_type=str,
        scope=Scope(parent=BUILTIN_CLASS_SCOPES[str]),
    ),
    str.upper:FunctionHeader(
        name="upper",
        return_type=str,
        scope=Scope(parent=BUILTIN_CLASS_SCOPES[str]),
    ),
}

class TestCase:
    def __init__(self,filename,should_fail,name:Optional[str]=None,debug:bool=False):
        self.filename=filename
        self.should_fail=should_fail
        self.name=name
        self.debug=debug

def verify_files(cases:List[TestCase]):
    num_fail=0
    num_ok=0
    for case in cases:
        exception=None
        try:
            full_filename=Path(os.path.dirname(__file__))/case.filename
            ModuleChecker(str(full_filename),print_ast=case.debug)
            failed=False
        except ValueError as e:
            exception=e
            failed=True
        except Exception as e:
            raise e

        if int(failed)+int(case.should_fail)==1:
            if failed:
                mismatch_cause="failed but should not have"
            else:
                mismatch_cause="did not fail but should have"

            print(f"x {case.name or case.filename} ({mismatch_cause})")

            num_fail+=1
            try:
                print(f"test failed with:\n{(str(exception))}")
            except:
                pass
        else:
            print(f"o {case.name or case.filename}")
            num_ok+=1

    print("-"*32)
    print(f"{num_ok}/{num_ok+num_fail} ok ({((num_ok)/(num_ok+num_fail)*100):5.1f}%)")

if __name__=="__main__":
    verify_files([
        TestCase("tests/func_ret_match.py",False),
        TestCase("tests/func_ret_mismatch.py",True),
        TestCase("tests/binop_add_intint.py",False),
        TestCase("tests/func_ret_multiple_transitive_int.py",False),
        TestCase("tests/func_ret_arg.py",False),
        TestCase("tests/func_ret_transitive_int.py",False),
        TestCase("tests/lotsofstuff.py",False),
    ])