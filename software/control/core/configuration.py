import os

# qt libraries
from qtpy.QtCore import QObject

from control._def import *

import json
from pathlib import Path
import control.utils_config as utils_config

from typing import Optional, List, Union, Tuple, Any

@TypecheckClass
class Configuration:
    """ illumination channel configuration """

    mode_id:int
    name:str
    camera_sn:str
    exposure_time:float # in ms
    analog_gain:float
    illumination_source:int
    illumination_intensity:float # percent light source power/intensity
    channel_z_offset:Optional[float]=None

    def set_exposure_time(self,new_value:float):
        self.exposure_time=new_value
    def set_analog_gain(self,new_value:float):
        self.analog_gain=new_value
    def set_offset(self,new_value:float):
        self.channel_z_offset=new_value
    def set_illumination_intensity(self,new_value:float):
        self.illumination_intensity=new_value

    def automatic_tooltip(self)->str:
        if self.name.startswith("Fluorescence"):
            excitation_wavelength=self.name.split(" ")[1]
            return f"Imaging mode where the sample is excited with light at a wavelength of {excitation_wavelength}nm. The camera then records all the light that is emitted from the sample (e.g. via fluorescence)."
        else:
            return "no description for this channel"

    def as_dict(self):
        return {
            "ID":self.mode_id,
            "Name":self.name,
            "IlluminationSource":self.illumination_source,
            "ExposureTime":self.exposure_time,
            "AnalogGain":self.analog_gain,
            "IlluminationIntensity":self.illumination_intensity,
            "CameraSN":self.camera_sn,
            "RelativeZOffsetUM":self.channel_z_offset,
        }

    def from_json(s:dict)->"Configuration":
        return Configuration(
            mode_id=s["ID"],
            name=s["Name"],
            illumination_source=s["IlluminationSource"],
            exposure_time=s["ExposureTime"],
            analog_gain=s["AnalogGain"],
            illumination_intensity=s["IlluminationIntensity"],
            camera_sn=s["CameraSN"],
            channel_z_offset=s["RelativeZOffsetUM"],
        )

class ConfigurationManager(QObject):
    @property
    def num_configurations(self)->int:
        return len(self.configurations)

    def __init__(self,filename):
        QObject.__init__(self)
        self.config_filename:str = filename
        self.configurations:List[Configuration] = []
        self.read_configurations(self.config_filename)
        
    def save_configurations(self):
        self.write_configuration(self.config_filename)

    def as_json(self)->list:
        return [
            config.as_dict() 
            for config 
            in self.configurations
        ]

    def config_by_name(self,name:str)->Configuration:
        for config in self.configurations:
            if config.name==name:
                return config
        raise ValueError(f"no config found with name {name}")

    def write_configuration(self,filename:str):
        json_tree_string=json.encoder.JSONEncoder(indent=2).encode({ 'channel_config':self.as_json() })
        with open(filename, mode="w", encoding="utf-8") as json_file:
            json_file.write(json_tree_string)

    def read_configurations(self,filename:str):
        with open(filename,mode="r",encoding="utf-8") as json_file:
            json_tree=json.decoder.JSONDecoder().decode(json_file.read())

        self.load_configuration_from_json_list(json_tree['channel_config'])

    def load_configuration_from_json_list(self,json_list:List[dict]):
        self.configurations=[Configuration.from_json(item) for item in json_list]
