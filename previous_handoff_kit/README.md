# Q → Claude 引継ぎキット

**これは正式なQRC書込・実行接続を実装したものではありません。** Claudeに渡す引継ぎ指示と、既知のWindowsディレクトリから証拠を読み取り回収するスクリプトです。

## 最短手順
1. ZIPをWindowsへ展開。
2. PowerShellで展開先に移動し、次を実行:
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\collect_q_handoff.ps1 -IncludeSource`
3. デスクトップの `Q_Claude_Handoff\Q_HANDOFF_EVIDENCE_*.zip` をClaude Desktopに添付。
4. `CLAUDE_HANDOFF_PROMPT.md` の全文をClaudeへ送信。

## 実行範囲
- 既知の2つのQRC/Gatewayフォルダのみ読取。実注文、ファイル改変、QRC停止、認証変更はしない。
- ファイル名で秘密情報を除外するが、**中身に秘密がない保証はない**。外部アップロード前に内容を確認すること。
- Q本体の全ファイルは収集しない。ClaudeにはGitHub正本への接続も別途必要。
- 現物の存在・接続・Claude動作は未検証。`NOT_PROVEN`はそのまま維持する。
