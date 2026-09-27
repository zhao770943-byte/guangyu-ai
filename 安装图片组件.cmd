@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python 启动器 py。请安装 Python 3.11 或以上，并向启动程序使用的 Python 环境安装 requirements.txt。
  pause
  exit /b 1
)
echo 正在为 py -3 对应的 Python 安装图片校验组件，此步骤需要联网。
py -3 -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo 安装未完成。请检查上方错误与网络连接；没有修改工作台数据。
  pause
  exit /b 1
)
echo 图片组件安装完成。可启动光屿 AI 后上传参考图、首帧或尾帧。
pause
