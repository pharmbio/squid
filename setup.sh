# installing prerequisite software packages
sudo usermod -aG dialout $USER # allow communication with arduino boards without superuser access
sudo apt update
sudo apt install -y tree curl git htop xclip # basic tools that should be installed
sudo apt install -y python3-pip python3-pyqtgraph python3-pyqt5 # squid software dependencies
sudo apt install -y libreoffice virtualenv make gcc build-essential libgtk-3-dev openjdk-11-jdk-headless default-libmysqlclient-dev libnotify-dev libsdl2-dev # dependencies for cellprofiler
sudo snap install --classic code # install visual studio code

# set environmental variables required for cellprofiler installation
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export PATH=$PATH:/home/ubuntu/.local/bin

# install everything relative to home
cd ~

# install micro, a great terminal text editor (from .deb file instead of apt repo because the version in apt creates a trash log.txt file in wd whenever the editor is opened)
wget https://github.com/zyedidia/micro/releases/download/v2.0.11/micro-2.0.11-amd64.deb
sudo dpkg -i micro-2.0.11-amd64.deb

# setup microscope python env (which is global env, since Qt is used for gui, which does not work inside virtualenv)
pip3 install --upgrade setuptools pip
# python dependencies for squid software (PyQt5 might not actually be required? seems like it is already installed via python3-pyqt5, same for pyqtgraph)
pip3 install Pillow==9.3.* PyQt5==5.14.* pyqtgraph==0.12.* QtPy==2.2.* scipy==1.9.* numpy==1.23.* matplotlib pyserial pandas imageio opencv-python opencv-contrib-python lxml crc scikit-image tqdm

# install orange
virtualenv orange_venv
source orange_venv/bin/activate
pip3 install --upgrade setuptools pip
pip3 install orange3
deactivate

# install cellprofiler
virtualenv cellprofiler_venv
source cellprofiler_venv/bin/activate
pip3 install numpy==1.23 matplotlib qtpy pyserial pandas imageio opencv-python opencv-contrib-python lxml crc # python dependencies for squid software, installed into cellprofiler virtualenv
# download prebuilt wxpython wheel to avoid local compilation which takes 30 minutes
wget https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-20.04/wxPython-4.1.0-cp38-cp38-linux_x86_64.whl
pip3 install wxPython-4.1.0-cp38-cp38-linux_x86_64.whl
pip3 install cellprofiler==4.2.4 # numpy needs to be done installing before cellprofiler is installed
deactivate

# install cellprofiler analyst
virtualenv cellprofileranalyst_venv
source cellprofileranalyst_venv/bin/activate
pip3 install numpy==1.23 pandas seaborn scikit-learn verlib python-javabridge python-bioformats
pip3 install wxPython-4.1.0-cp38-cp38-linux_x86_64.whl
wget https://github.com/CellProfiler/CellProfiler-Analyst/archive/refs/tags/3.0.4.tar.gz -O cpa304.tar.gz
tar -xf cpa304.tar.gz
pip3 install ./CellProfiler-Analyst-3.0.4
# for some reason these icons are not copied during installation (which crashes the program on startup)
cp CellProfiler-Analyst-3.0.4/cpa/icons/* cellprofileranalyst_venv/lib/python3.8/site-packages/cpa/icons/
deactivate

# install microscope software (and firmware)
cd ~/Downloads
git clone https://github.com/pharmbio/squid # download squid software and firmware repo
# from https://forum.squid-imaging.org/t/setting-up-arduino-teensyduino-ide-for-uploading-firmware/36 :
# download arduino IDE
curl https://downloads.arduino.cc/arduino-1.8.19-linux64.tar.xz -o arduino-1.8.19.tar.xz
tar -xf arduino-1.8.19.tar.xz
# install arduino udev rules for arduino board communication
curl https://www.pjrc.com/teensy/00-teensy.rules -o 00-teensy.rules 
sudo cp 00-teensy.rules /etc/udev/rules.d/
# install teensyduino board package (teensy4.1 is used inside the microscopes)
curl https://www.pjrc.com/teensy/td_157/TeensyduinoInstall.linux64 -o teensyduino-install.linux64
chmod +x teensyduino-install.linux64
./teensyduino-install.linux64 --dir=arduino-1.8.19
cd arduino-1.8.19
# install arduino IDE (incl. teensyduin)
chmod +x install.sh
sudo ./install.sh

# install/upgrade microscope firmware
echo "manual instructions: in the now open window, manually comment #include 'def_octopi.h' and uncomment #include 'def_octopi_80120.h', then switch to correct board (teensy 4.1) then install the packages PacketSerial and FastLED (both in Tools), then flash firmware"
cd ~/Downloads/squid/firmware/octopi_firmware_v2/main_controller_teensy41
arduino main_controller_teensy41.ino
# copy default microscope configuration file - requires adjustment of well positions and autofocus channel
cd ~/Downloads/squid/software
cp configurations/configuration_HCS_v2.txt configuration.txt
# install camera driver
cd ~/Downloads/squid/software/drivers\ and\ libraries/daheng\ camera/Galaxy_Linux-x86_Gige-U3_32bits-64bits_1.2.1911.9122
echo -e "\ny\nEn\n" | sudo ./Galaxy_camera.run
cd ~/Downloads/squid/software/drivers\ and\ libraries/daheng\ camera/Galaxy_Linux_Python_1.0.1905.9081/api
python3 setup.py build
sudo python3 setup.py install

cd # to home directory

# set up bash commands to run installed software
echo '
run_microscope() {
  cd ~/Downloads/squid/software
  python3 main_hcs.py
}
run_cellprofiler() {
  source ~/cellprofiler_venv/bin/activate
  python3 -m cellprofiler
  deactivate
}
run_cellprofileranalyst() {
  source ~/cellprofileranalyst_venv/bin/activate
  python3 ~/CellProfiler-Analyst-3.0.4/CellProfiler-Analyst.py
  deactivate
}
run_orange() {
  source ~/orange_venv/bin/activate
  python3 -m Orange.canvas
  deactivate
}
' >> ~/.bashrc
source ~/.bashrc

# create scripts to run certain software in their respective environment
echo '#!/bin/bash
source /home/pharmbio/cellprofiler_venv/bin/activate
python3 -m cellprofiler
deactivate
' > ~/Documents/cellprofiler.sh
echo '#!/bin/bash
source /home/pharmbio/cellprofileranalyst_venv/bin/activate
python3 ~/CellProfiler-Analyst-3.0.4/CellProfiler-Analyst.py
deactivate
' > ~/Documents/cellprofileranalyst.sh
echo '#!/bin/bash
cd /home/pharmbio/Downloads/squid/software
python3 main_hcs.py
sleep 10
' > ~/Documents/microscope.sh
echo '#!/bin/bash
source /home/pharmbio/orange_venv/bin/activate
python3 -m Orange.canvas
deactivate
' > ~/Documents/orange.sh

# add desktop icons to start the installed software (incl. microscope)
echo '[Desktop Entry]
Type=Application
Terminal=false
Name=cellprofiler
Icon=utilities-terminal
Exec=/home/pharmbio/Documents/cellprofiler.sh
Categories=Application;
' > ~/Desktop/cellprofiler.desktop
echo '[Desktop Entry]
Type=Application
Terminal=false
Name=cellprofiler analyst
Icon=utilities-terminal
Exec=/home/pharmbio/Documents/cellprofileranalyst.sh
Categories=Application;
' > ~/Desktop/cellprofileranalyst.desktop
echo '[Desktop Entry]
Type=Application
Terminal=true
Name=microscope
Icon=utilities-terminal
Exec=/home/pharmbio/Documents/microscope.sh
Categories=Application;
' > ~/Desktop/microscope.desktop
echo '[Desktop Entry]
Type=Application
Terminal=false
Name=orange
Icon=utilities-terminal
Exec=/home/pharmbio/Documents/orange.sh
Categories=Application;
' > ~/Desktop/orange.desktop

chmod 755 ~/Desktop/orange.desktop ~/Documents/orange.sh
chmod 755 ~/Desktop/microscope.desktop ~/Documents/microscope.sh
chmod 755 ~/Desktop/cellprofiler.desktop ~/Documents/cellprofiler.sh
chmod 755 ~/Desktop/cellprofileranalyst.desktop ~/Documents/cellprofileranalyst.sh

# remove install files
cd
rm teensyduino-install.linux64 00-teensy.rules arduino-1.8.19.tar.xz micro-2.0.11-amd64.deb