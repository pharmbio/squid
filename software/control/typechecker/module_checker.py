"""
- dynamic typing of variables is not allowed. if a symbol of any type is already present in the current (or any parent) scope, assigning a value of any type that is incompatible with the existing type information is invalid.
"""

import ast, sys, typing, os
from pathlib import Path

from typing import Union, List, Optional, Tuple, Any, Dict, Set

from util import type_name, TypeCheckResult

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
    ):
        self.name=name
        self.return_type=return_type

        self.posonlyargs=posonlyargs
        self.args=args
        self.kwonlyargs=kwonlyargs

        self.starargs=starargs
        self.starkwargs=starkwargs

        self.args_with_default_values=args_with_default_values

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
    )
}


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
        self.left_topype=op
    def __str__(self):
        return "incompatible bin op types"
        
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
        if self.old_node is None:
            return f"{self.new_node.id} already exists"
        else:
            return f"{self.new_node.id} already exists, previous definition in line {self.old_node.lineno}"
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
    def __init__(self,node,container_type):
        super().__init__(node=node)
        self.container_type=container_type
    def __str__(self):
        return f"type {type_name(self.node.name)} does not have attribute {self.container_type.attr}"

def typecheck_assignment(node,left_type,right_type)->TypeCheckResult:
    if left_type==right_type:
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

        code_str:Optional[str]=None,
    ):
        self.parent=parent
        self.known_symbol_types={}
        self.can_return=can_return
        self.must_return=must_return
        self.return_type=return_type
        self.in_loop=in_loop
        self.location=location
        if self.parent is None:
            assert not code_str is None, "the topmost scope must have the source code attached"
            self.code_str=code_str
        else:
            assert code_str is None, "only the topmost scope must have the source code attached"
            self.code_str=self.parent.code_str

        self.is_class=False

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

    def highlighted_error_location(self,node):
        if node is None:
            return self.full_location

        statement_code_location=f"  line {node.lineno} : "
        
        statement_code_text=self.code_str.splitlines()[node.lineno-1]

        code_highlight=(" "*(len(statement_code_location)+node.col_offset))+("^"*(node.end_col_offset-node.col_offset))

        return f"{self.full_location}\n{statement_code_location}{statement_code_text}\n{code_highlight}"

    def resolve_symbol_name_to_type(self,symbol):
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

    def eval_value_type(self,value):
        if isinstance(value,ast.Constant):
            return type(value.value)

        elif isinstance(value,ast.Name):
            name=value.id
            if name in self.known_symbol_types:
                return self.known_symbol_types[name]
            elif name in BUILTIN_FUNCTION_ANNOTATIONS:
                return BUILTIN_FUNCTION_ANNOTATIONS[name]
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
                if container_type.attr in container_type.__dict__:
                    return type(container_type.__dict__[container_type.attr])
            elif isinstance(container_type,ClassChecker):
                class_type=container_type
                if value.attr in class_type.scope.known_symbol_types:
                    return class_type.scope.known_symbol_types[value.attr]
            
            raise UnknownAttribute(node=value,container_type=container_type)
        
        assert False,f"unknown type {ast.dump(value)}"
    
    def type_annotation_to_type(self,type_annotation:Union[None,ast.Name,Any]):
        if type_annotation is None:
            return None

        if isinstance(type_annotation,ast.Name):
            if type_annotation.id in BUILTIN_TYPE_NAMES:
                return BUILTIN_TYPE_NAMES[type_annotation.id]
            elif type_annotation.id in self.known_symbol_types:
                return self.known_symbol_types[type_annotation.id]
            elif not self.parent is None:
                return self.parent.type_annotation_to_type(type_annotation)
            
            raise UnknownSymbol(type_annotation.id,node=type_annotation)

        elif isinstance(type_annotation,ast.Constant):
            if type_annotation.value is None:
                return None
            
            raise ExpectedType(node=type_annotation)
        else:
            assert False,f"unknown type {ast.dump(type_annotation)}"

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


    def validate_statements(self,nodes):
        try:
            for node in nodes:
                self.validate_statement(node)

            if len(nodes)>=1:
                if self.can_return and (not self.return_type is None) and self.must_return and not isinstance(node,ast.Return):
                    raise MissingReturn(node)

        except TypeCheckError as t:
            raise ValueError(self.highlighted_error_location(t.node)+"\n"+str(t))

    def validate_statement(self,statement):
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
            if not bin_op_result_type(left_type,right_type,statement.op,strict_type_compatiblity=True)==left_type:
                raise IncompatibleBinOpTypes(left_type,right_type,statement.op)

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
            raise Exception(f"importing modules is not supported (importing module(s) '{','.join([i.name for i in statement.names])}' here)")

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

            if class_name in self.known_symbol_types:
                raise SymbolAlreadyExists(new_node=statement)

            class_scope=Scope(parent=self)
            class_checker_object=ClassChecker(statement,class_scope)

            self.known_symbol_types[class_name]=class_checker_object

            for decorator in statement.decorator_list:
                print(f"found decorator {decorator} for classdef")

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

            class_scope.validate_statements(statement.body)

        else:
            assert False, f"unimplemented {statement}"

class ClassChecker:
    def __init__(self,class_def_node,class_scope):
        self.node=class_def_node
        self.scope=class_scope

        assert not self.scope.is_class
        self.scope.is_class=True

        self.scope.known_symbol_types["Self"]=self

class FunctionChecker:
    def __init__(self,parent_module,function):
        self.parent_scope=parent_module

        self.function=function
        self.name=self.function.name

        self.scope=Scope(self.parent_scope,can_return=True,must_return=True,in_loop=False,location=f"function '{self.function.name}'")
        self.scope.return_type=self.scope.type_annotation_to_type(function.returns)

        self.arguments=[]

        # handle function.args.{vararg is *arg, kwarg is **kwargs}
        for arg in function.args.posonlyargs:
            arg_type=self.scope.type_annotation_to_type(arg.annotation)
            self.scope.known_symbol_types[arg.arg]=arg_type

        for arg in function.args.args:
            arg_type=self.scope.type_annotation_to_type(arg.annotation)
            self.scope.known_symbol_types[arg.arg]=arg_type

        for arg in function.args.kwonlyargs:
            arg_type=self.scope.type_annotation_to_type(arg.annotation)
            self.scope.known_symbol_types[arg.arg]=arg_type

        self.scope.validate_statements(function.body)

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

        target_ast=ast.parse(self.file_contents)

        if print_ast:
            print(ast.dump(target_ast))

        self.scope.validate_statements(target_ast.body)

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