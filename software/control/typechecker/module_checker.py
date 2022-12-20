"""
- dynamic typing of variables is not allowed. if a symbol of any type is already present in the current (or any parent) scope, assigning a value of any type that is incompatible with the existing type information is invalid.
"""

import ast, sys, typing, os
from pathlib import Path

from typing import Union, List, Optional, Tuple, Any

def exit_on_message(message,exit_code:int=-1):
    print(message)
    sys.exit(exit_code)

from util import type_name, TypeCheckResult

class TypeCheckError(Exception):
    def __init__(self,node=None):
        super().__init__()
        self.node=node

class TypesUnequal(TypeCheckError):
    def __init__(self,expected_type,got_type,**kwargs):
        super().__init__(**kwargs)
        self.expected_type=expected_type
        self.got_type=got_type
    def __str__(self):
        return f"expected type {type_name(self.expected_type)} got instead {type_name(self.got_type)}"
        
class UnknownSymbol(TypeCheckError):
    def __init__(self,symbol_name:str,**kwargs):
        super().__init__(**kwargs)
        self.symbol_name=symbol_name
    def __str__(self):
        return f"unknown symbol '{self.symbol_name}'"

class FunctionArgumentMissing(TypeCheckError):
    def __init__(self,func,arg,site):
        super().__init__(node=site)
        self.arg=arg
    def __str__(self):
        return f"missing argument '{self.arg}'"

def typecheck_assignment(left_type,right_type)->TypeCheckResult:
    if left_type==right_type:
        return TypeCheckResult(True)

    raise TypesUnequal(left_type,right_type)

def bin_op_result_type(left_type,right_type,op):
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
            if left_type == float or right_type==float:
                return float

            assert False, "unreachable"
    # ops always promoting to float
    elif isinstance(op,(
        ast.Div,
    )):
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
    def __init__(self,parent=None):
        self.parent=parent
        self.known_symbol_types={}

    def eval_value_type(self,value):
        if isinstance(value,ast.Constant):
            return type(value.value)
        elif isinstance(value,ast.Name):
            name=value.id
            if name in self.known_symbol_types:
                return self.known_symbol_types[name]
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
            func_type=self.resolve_symbol_name_to_type(value.func)

            try:
                starargs=value.starargs
            except:
                starargs=None
            try:
                kwargs=value.kwargs
            except:
                kwargs=None

            return self.validate_function_call(
                func_type=func_type,
                args=value.args,
                keywords=value.keywords,
                starargs=starargs,
                kwargs=kwargs,
                call_node=value
            )
        
        assert False,f"unknown type {value}"

    def resolve_symbol_name_to_type(self,symbol):
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
    
    def type_annotation(self,type_annotation):
        if type_annotation is None:
            return None

        if isinstance(type_annotation,ast.Name):
            return {
                'None':None,

                'bool':bool,
                'int':int,
                'float':float,
            }[type_annotation.id]
        else:
            assert False,f"unknown type {type_annotation}"

    def validate_function_call(self, 
        func_type, # currently implemented as FunctionChecker
        args:list, # meaning arguments passed as positional arguments
        keywords:List[ast.keyword], # meaning arguments passed by keyword
        starargs:Optional[Any], # meaning *args
        kwargs:Optional[Any], # meaning **kwargs

        call_node:ast.Call,
    )->type:
        func_args=func_type.get_args()
        args_accounted_for={arg[0]:False for arg in func_args}

        for pos,pos_arg in enumerate(args):
            arg_name,arg_type=func_args[pos]
            left_type=arg_type

            right_type=self.eval_value_type(pos_arg)
            try:
                typecheck_assignment(left_type,right_type)
            except TypeCheckError as t:
                t.node=pos_arg
                raise t

            args_accounted_for[arg_name]=True

        func_kw_args=func_type.get_kwargs()
        for kw in keywords:
            assert kw.arg in func_kw_args
            func_arg_type=func_kw_args[kw.arg]
            left_type=func_arg_type

            right_type=self.eval_value_type(kw.value)

            try:
                typecheck_assignment(left_type,right_type)
            except TypeCheckError as t:
                t.node=kw
                raise t

            args_accounted_for[kw.arg]=True
            
        if not starargs is None and len(starargs)>0:
            assert False, "unimplemented"
        if not kwargs is None and len(kwargs)>0:
            assert False, "unimplemented"

        for arg,accounted_for in args_accounted_for.items():
            if not accounted_for:
                print(f"arg {arg}")
                raise FunctionArgumentMissing(func=func_type,arg=arg,site=call_node)

        return func_type.return_type

class FunctionChecker:
    def __init__(self,parent_module,function):
        self.parent_module=parent_module

        self.scope=Scope(self.parent_module.scope)

        self.function=function

        self.name=function.name
        self.return_type=self.scope.type_annotation(function.returns)
        self.arguments=[]

        # handle function.args.{vararg is *arg, kwarg is **kwargs, defaults, kw_defaults}
        for arg in function.args.posonlyargs:
            arg_type=self.scope.type_annotation(arg.annotation)
            self.scope.known_symbol_types[arg.arg]=arg_type

        for arg in function.args.args:
            arg_type=self.scope.type_annotation(arg.annotation)
            self.scope.known_symbol_types[arg.arg]=arg_type

        for arg in function.args.kwonlyargs:
            arg_type=self.scope.type_annotation(arg.annotation)
            self.scope.known_symbol_types[arg.arg]=arg_type

        for statement in function.body:
            try:
                self.validate_statement(statement)
            except UnknownSymbol as u:
                error_msg="unknown symbol in "+self.highlighted_error_location(u.node)+"\n  "+str(u)
                self.parent_module.exit_on_message(error_msg)
            except TypesUnequal as t:
                error_msg="type mismatch in "+self.highlighted_error_location(t.node)+"\n  "+str(t)
                self.parent_module.exit_on_message(error_msg)

    def get_args(self)->list:
        return [
            *[
                (arg.arg,self.scope.resolve_symbol_name_to_type(arg.arg))
                for arg
                in self.function.args.posonlyargs
            ],
            *[
                (arg.arg,self.scope.resolve_symbol_name_to_type(arg.arg))
                for arg
                in self.function.args.args
            ],
            *[
                (arg.arg,self.scope.resolve_symbol_name_to_type(arg.arg))
                for arg
                in self.function.args.kwonlyargs
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

    def validate_statement(self,statement):
        if isinstance(statement,ast.Return):
            return_value=statement.value

            try:
                right_type=self.scope.eval_value_type(return_value)
            except FunctionArgumentMissing as f:
                full_message=f"function argument missing {self.highlighted_error_location(node=f.node)}\n{str(f)}"
                self.parent_module.exit_on_message(full_message)

            try:
                res=typecheck_assignment(left_type=self.return_type,right_type=right_type)
            except TypesUnequal:
                left_type_str=type_name(self.return_type)
                right_type_str=type_name(right_type)

                full_message=f"return type mismatch {self.highlighted_error_location(node=statement)}\n  expected '{left_type_str}' but got '{right_type_str}' instead"
                self.parent_module.exit_on_message(full_message)

        elif isinstance(statement,ast.Assign):
            assignment=statement

            if len(assignment.targets)==1:
                target=assignment.targets[0]

                right_type=self.scope.eval_value_type(assignment.value)
                try:
                    left_type=self.scope.eval_value_type(target)
                    new_symbol_inserted=False
                except UnknownSymbol as u:
                    new_symbol_inserted=True
                    self.scope.known_symbol_types[u.symbol_name]=right_type

                if not new_symbol_inserted:
                    try:
                        res=typecheck_assignment(left_type,right_type)
                    except TypesUnequal:
                        full_message=f"type mismatch {self.highlighted_error_location(assignment)}\nvalue of type {type_name(right_type)} cannot be assigned to symbol {target.id} of type {type_name(left_type)}"
                        self.parent_module.exit_on_message(full_message)
                
            else:
                print("assignment with multiple targets not yet supported")
        else:
            assert False, f"unimplemented {statement}"

    def highlighted_error_location(self,node):
        error_main_text_and_location=f"in {self.filename} in function '{self.function.name}'"

        if node is None:
            return error_main_text_and_location

        statement_code_location=f"  line {node.lineno} : "
        
        statement_code_text=self.file_contents.splitlines()[node.lineno-1]

        code_highlight=(" "*(len(statement_code_location)+node.col_offset))+("^"*(node.end_col_offset-node.col_offset))

        return f"{error_main_text_and_location}\n{statement_code_location}{statement_code_text}\n{code_highlight}"

    @property
    def filename(self):
        return self.parent_module.filename
    @property
    def file_contents(self):
        return self.parent_module.file_contents

class ModuleChecker:
    def __init__(self,filename:str,fail_recoverable:bool=False,print_ast:bool=False):
        self.filename=filename
        self.fail_recoverable=fail_recoverable
        self.scope=Scope()

        with open(filename,"r",encoding="utf8") as target_file:
            self.file_contents=target_file.read()

        target_ast=ast.parse(self.file_contents)

        if print_ast:
            print(ast.dump(target_ast))

        for node in target_ast.body:
            if isinstance(node,ast.FunctionDef):
                function=FunctionChecker(self,node)

                if function.name in self.scope.known_symbol_types:
                    self.exit_on_message(f"a function with name {function.name} already exists in {self.filename}\n  first definition in line {self.scope.known_symbol_types[function.name].function.lineno}\n  second definition in line {function.function.lineno}")

                self.scope.known_symbol_types[function.name]=function

    def exit_on_message(self,full_message):
        if self.fail_recoverable:
            raise ValueError(full_message)
        else:
            exit_on_message(full_message)

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
            ModuleChecker(str(full_filename),fail_recoverable=True,print_ast=case.debug)
            failed=False
        except TypeCheckError as e:
            exception=e
            failed=True
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

    print("-"*16)
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