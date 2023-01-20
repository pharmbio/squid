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

def seconds_to_long_time(sec:float)->str:
    hours=int(sec//3600)
    sec-=hours*3600
    minutes=int(sec//60)
    sec-=minutes*60
    return f"{hours!s:3}h {minutes:2}m {sec:4.1f}s"

class Configuration:
    """ illumination channel configuration """

    mode_id:str
    name:str
    camera_sn:str
    exposure_time:float
    analog_gain:float
    illumination_source:int
    illumination_intensity:float
    channel_z_offset:float

    def __init__(self,
        mode_id:str,
        name:str,
        camera_sn:str,
        exposure_time:float,
        analog_gain:float,
        illumination_source:int,
        illumination_intensity:float,
    ):
        self.mode_id = mode_id
        self.name = name
        self.camera_sn = camera_sn
        self.exposure_time = exposure_time
        self.analog_gain = analog_gain
        self.illumination_source = illumination_source
        self.illumination_intensity = illumination_intensity

    def set_exposure_time(self,new_value:float):
        self.exposure_time=new_value

    def set_analog_gain(self,new_value:float):
        self.analog_gain=new_value

    def set_offset(self,new_value:float):
        self.channel_z_offset=new_value

    def set_illumination_intensity(self,new_value:float):
        self.illumination_intensity=new_value

    @property
    def automatic_tooltip(self)->str:
        if self.name.startswith("Fluorescence"):
            excitation_wavelength=self.name.split(" ")#[1]
            return f"Imaging mode where the sample is excited with light at a wavelength of {excitation_wavelength}nm. The camera then records all the light that is emitted from the sample (e.g. via fluorescence)."
        else:
            return "no description for this channel"

import typechecker as tc

import import_me
import math

import typing

@tc.module_checker.annotation_block
class annotate:
    class import_me:
        class Person:
            def __init__(self,name:str):pass
            def get_age(self)->int:pass

    class math:
        @tc.module_checker.private
        class private:
            IntegralType=typing.Union[int,float]

        def acos(n:private.IntegralType)->private.IntegralType: pass

im_peter=import_me.Person(name="peter")
im_peter_age:int=im_peter.get_age()
num=math.acos(3)