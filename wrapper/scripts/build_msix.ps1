# build_msix.ps1 - MSIX パッケージ生成の雛形
# 1. PyInstaller で実行ファイルを作成
# 2. makeappx.exe で MSIX パッケージ化
# 3. signtool.exe で署名

param(
    [string]$CertPath,
    [string]$CertPassword
)

# Step1: exe 化 (例)
# pyinstaller --add-data "..\whisperlivekit\web;whisperlivekit/web" `
#   --name whisperlivekit-wrapper wrapper/cli/main.py

# Step2: MSIX パック (例)
# makeappx.exe pack /d dist/whisperlivekit-wrapper /p dist/whisperlivekit-wrapper.msix

# Step3: 署名 (例)
# signtool.exe sign /fd SHA256 /f $CertPath /p $CertPassword dist/whisperlivekit-wrapper.msix
