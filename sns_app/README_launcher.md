# Launcher (tk_launcher)

`tk_launcher.py` は `sns_app` パッケージ内で動作する Tkinter ランチャーです。

機能:
- サーバ起動 (`python -m sns_app.app` をバックグラウンドで起動)
- ブラウザでローカルサイトを開く
- サーバ停止

使い方:
```powershell
python -m sns_app.tk_launcher
```

注意: Windows環境では、バックグラウンドで起動した Flask の標準出力/エラーはこのランチャーからは見えません。デバッグ時は別ターミナルで `python -m sns_app.run` を使って起動してください。
