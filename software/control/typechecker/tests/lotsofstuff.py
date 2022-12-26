def mult(a:int,b:int)->int:
    return a*b

def div(a:int,b:int)->float:
    return a/b

def div2(a:int,b:float)->int:
    return a//a

def calls_other_function(a:int)->int:
    return mult(a,a)

def calls_other_function_also(a:int)->int:
    return mult(a=a,b=a)

def calls_other_function_alsoalso(a:int)->int:
    ret=mult(a,a)+mult(a,a)
    return ret

def anotherfunction(a:int)->int:
    ret=2
    ret=ret+3
    return ret

def anotherfunction2(a:int)->int:
    ret=2
    ret+=3
    return ret

def functionwithifstatement()->int:
    a=3
    if a:
        return 3
    elif 3:
        return a
    
    return 4

def function_with_while_loop()->int:
    while True:
        return 1
        continue

    return 0

somemoduleglobalvar=2

def function_using_moduleglobalvar()->int:
    return somemoduleglobalvar

def multiple_assignment():
    a=b=2
    a=3
    b=4

class Person:
    name:str

    def __init__(self,name:str):
        self.name=name

    def sayhi(self,b:float=2.0,a:int=2)->str:
        return self.name

peter=Person(name="peter")
_=peter.sayhi()
