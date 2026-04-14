# 安装FaustBot

如果在安装过程中出现问题，可以把窗口中显示的所有文字，以及这个文件交给任何AI寻求帮助

## 1.下载项目文件

进入 [liwusen/FaustBot-llm-vtuber: FaustBot LLM Vtuber/桌宠](https://github.com/liwusen/FaustBot-llm-vtuber)

![description](.\assets\download_zip.png)

点击 Download Zip,将下载后的Zip解压到一个文件夹中备用

或者你也可以选择使用Git

```batch
git clone https://github.com/liwusen/FaustBot-llm-vtuber
```

## 2.安装前置

### 2.1 Node.js

下载[Node.js Installer](https://nodejs.org/dist/v24.14.1/node-v24.14.1-x64.msi),这是Node.js的官方安装程序
完成安装后，找到Windows Powershell,输入

```batch
node -v
```

按下Enter,出现

![nodejs版本为v24......](D:\dev\faustbot\faust\document\assets\nodejs_version.png)

即代表安装成功

### 2.2 Anaconda

请参考[Anaconda介绍、安装及使用教程 - 简书](https://www.jianshu.com/p/62f155eb6ac5)完成Anaconda 安装

打开Powershell应用，输入

```batch
conda -v
```

按下回车

![conda_version.png](D:\dev\faustbot\faust\document\assets\conda_version.png)

注:如果出现错误，可以尝试执行`conda init`后重新打开窗口，在试一次

随后输入

```batch
conda create -n faustbot python=3.11 -y
conda install ffmpeg -y
```

### 3.[重要]本地AI推理/AI推理选择

在这一步，请检查你的GPU,如果是Nvidia GPU且显存大于6GB,那么你可以选择本地语音生成/识别推理，这允许你自由指定参考音频否则，请选择云端推理
经过实测，在5060上也可以取得较好体验

如果你选择本地推理，请进行步骤4.1，否则请执行步骤4.2

### 4.安装AI框架

### 4.1 云端推理

把以下命令复制到Powershell中执行:

```batch
conda activate faustbot
pip3 install torch
```

### 4.2 本地推理

把以下命令复制到Powershell中执行:

```batch
conda activate faustbot
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

## 5.进入解压到的文件夹，点击右键 “在终端中打开”,把以下命令复制到打开的窗口中

```batch
pip install"D:\dev\faustbot\faust\requirements.txt"
cd .\backend\minecraft\mc-operator
npm install
cd ..\..\..\
cd frontend
npm install
```
