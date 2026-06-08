@echo off
chcp 65001 >nul
echo ================================
echo  全站同品检测工具 - Windows构建
echo ================================
echo.

pip install -r requirements.txt
pip install pyinstaller

echo.
echo 开始打包...
pyinstaller --noconfirm --onefile --windowed ^
  --name "全站同品检测工具" ^
  --hidden-import=pandas ^
  --hidden-import=openpyxl ^
  --hidden-import=requests ^
  --collect-all pandas ^
  --collect-all openpyxl ^
  main.py

echo.
if exist "dist\全站同品检测工具.exe" (
    echo ✅ 构建成功！
    echo 输出文件: dist\全站同品检测工具.exe
) else (
    echo ❌ 构建失败，请检查错误信息
)
echo.
pause
