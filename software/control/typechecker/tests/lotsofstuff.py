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