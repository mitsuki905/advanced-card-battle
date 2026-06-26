@echo off
cd /d %~dp0

:: 1. venvフォルダがなければ作成する
if not exist venv (
    echo "venvフォルダがなければ作成する"
    python -m venv venv
)

:: 2. 仮想環境を有効化
echo "仮想環境を有効化"
call venv\Scripts\activate

:: 3. pipのアップグレード
echo "pipのアップグレード"
python -m pip install --upgrade pip

:: 4. パッケージのインストール
if exist requirements.txt (
    echo "パッケージのインストール"
    pip install -r requirements.txt
) else (
    echo "requirements.txtが存在しない"
)

echo.
echo "セットアップ完了"
pause