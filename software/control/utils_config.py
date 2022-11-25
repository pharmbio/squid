from lxml import etree as ET
top = ET.Element('modes') # type: ignore

def generate_default_configuration(filename):

    mode_1 = ET.SubElement(top,'mode') # type: ignore
    mode_1.set('ID','1')
    mode_1.set('Name','BF LED matrix full')
    mode_1.set('ExposureTime','12')
    mode_1.set('AnalogGain','0')
    mode_1.set('IlluminationSource','0')
    mode_1.set('IlluminationIntensity','5')
    mode_1.set('CameraSN','')
    mode_1.set('RelativeZOffsetUM','')

    mode_2 = ET.SubElement(top,'mode') # type: ignore
    mode_2.set('ID','2')
    mode_2.set('Name','BF LED matrix left half')
    mode_2.set('ExposureTime','16')
    mode_2.set('AnalogGain','0')
    mode_2.set('IlluminationSource','1')
    mode_2.set('IlluminationIntensity','5')
    mode_2.set('CameraSN','')
    mode_2.set('RelativeZOffsetUM','')

    mode_3 = ET.SubElement(top,'mode') # type: ignore
    mode_3.set('ID','3')
    mode_3.set('Name','BF LED matrix right half')
    mode_3.set('ExposureTime','16')
    mode_3.set('AnalogGain','0')
    mode_3.set('IlluminationSource','2')
    mode_3.set('IlluminationIntensity','5')
    mode_3.set('CameraSN','')
    mode_3.set('RelativeZOffsetUM','')

    mode_4 = ET.SubElement(top,'mode') # type: ignore
    mode_4.set('ID','4')
    mode_4.set('Name','BF LED matrix color PDAF')
    mode_4.set('ExposureTime','22')
    mode_4.set('AnalogGain','0')
    mode_4.set('IlluminationSource','3')
    mode_4.set('IlluminationIntensity','5')
    mode_4.set('CameraSN','')
    mode_4.set('RelativeZOffsetUM','')

    mode_5 = ET.SubElement(top,'mode') # type: ignore
    mode_5.set('ID','5')
    mode_5.set('Name','Fluorescence 405 nm Ex')
    mode_5.set('ExposureTime','100')
    mode_5.set('AnalogGain','10')
    mode_5.set('IlluminationSource','11')
    mode_5.set('IlluminationIntensity','100')
    mode_5.set('CameraSN','')
    mode_5.set('RelativeZOffsetUM','')

    mode_6 = ET.SubElement(top,'mode') # type: ignore
    mode_6.set('ID','6')
    mode_6.set('Name','Fluorescence 488 nm Ex')
    mode_6.set('ExposureTime','100')
    mode_6.set('AnalogGain','10')
    mode_6.set('IlluminationSource','12')
    mode_6.set('IlluminationIntensity','100')
    mode_6.set('CameraSN','')
    mode_6.set('RelativeZOffsetUM','')

    mode_7 = ET.SubElement(top,'mode') # type: ignore
    mode_7.set('ID','7')
    mode_7.set('Name','Fluorescence 638 nm Ex')
    mode_7.set('ExposureTime','100')
    mode_7.set('AnalogGain','10')
    mode_7.set('IlluminationSource','13')
    mode_7.set('IlluminationIntensity','100')
    mode_7.set('CameraSN','')
    mode_7.set('RelativeZOffsetUM','')

    mode_8 = ET.SubElement(top,'mode') # type: ignore
    mode_8.set('ID','8')
    mode_8.set('Name','Fluorescence 561 nm Ex')
    mode_8.set('ExposureTime','100')
    mode_8.set('AnalogGain','10')
    mode_8.set('IlluminationSource','14')
    mode_8.set('IlluminationIntensity','100')
    mode_8.set('CameraSN','')
    mode_8.set('RelativeZOffsetUM','')

    mode_12 = ET.SubElement(top,'mode') # type: ignore
    mode_12.set('ID','12')
    mode_12.set('Name','Fluorescence 730 nm Ex')
    mode_12.set('ExposureTime','50')
    mode_12.set('AnalogGain','10')
    mode_12.set('IlluminationSource','15')
    mode_12.set('IlluminationIntensity','100')
    mode_12.set('CameraSN','')
    mode_12.set('RelativeZOffsetUM','')

    mode_9 = ET.SubElement(top,'mode') # type: ignore
    mode_9.set('ID','9')
    mode_9.set('Name','BF LED matrix low NA')
    mode_9.set('ExposureTime','20')
    mode_9.set('AnalogGain','0')
    mode_9.set('IlluminationSource','4')
    mode_9.set('IlluminationIntensity','20')
    mode_9.set('CameraSN','')
    mode_9.set('RelativeZOffsetUM','')

    mode_10 = ET.SubElement(top,'mode') # type: ignore
    mode_10.set('ID','10')
    mode_10.set('Name','BF LED matrix left dot')
    mode_10.set('ExposureTime','20')
    mode_10.set('AnalogGain','0')
    mode_10.set('IlluminationSource','5')
    mode_10.set('IlluminationIntensity','20')
    mode_10.set('CameraSN','')
    mode_10.set('RelativeZOffsetUM','')

    mode_11 = ET.SubElement(top,'mode') # type: ignore
    mode_11.set('ID','11')
    mode_11.set('Name','BF LED matrix right dot')
    mode_11.set('ExposureTime','20')
    mode_11.set('AnalogGain','0')
    mode_11.set('IlluminationSource','6')
    mode_11.set('IlluminationIntensity','20')
    mode_11.set('CameraSN','')
    mode_11.set('RelativeZOffsetUM','')

    mode_12 = ET.SubElement(top,'mode') # type: ignore
    mode_12.set('ID','20')
    mode_12.set('Name','USB Spectrometer')
    mode_12.set('ExposureTime','20')
    mode_12.set('AnalogGain','0')
    mode_12.set('IlluminationSource','6')
    mode_12.set('IlluminationIntensity','0')
    mode_12.set('CameraSN','')
    mode_12.set('RelativeZOffsetUM','')

    tree = ET.ElementTree(top)
    tree.write(filename,encoding="utf-8", xml_declaration=True, pretty_print=True)