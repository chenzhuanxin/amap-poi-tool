@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动 高德 POI 预估与爬取工具...
echo 请稍候，浏览器将自动打开 http://127.0.0.1:8787
start "" http://127.0.0.1:8787
python app.py
pause
