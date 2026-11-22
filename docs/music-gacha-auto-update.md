# カワラボ楽曲ガチャ・MV自動更新

- 定期実行：毎週日曜 12:17 JST（GitHub ActionsのUTC表記では `17 3 * * 0`）
- 手動実行：GitHub → Actions → 「カワラボ楽曲ガチャ MV週次自動更新」→ Run workflow
- 取得元：FRUITS ZIPPER、CANDY TUNE、SWEET STEADY、CUTIE STREET、MORE STAR、KAWAII LAB. の公式YouTubeチャンネル（チャンネルIDは `scripts/update_music_gacha.py` に固定）
- 取得方法：各チャンネルの「動画」欄から最新120件を `yt-dlp` で照合。失敗時はYouTube公式RSSを利用（直近15件のみなので取りこぼす可能性あり）
- 自動登録条件：公式チャンネルの投稿で、タイトルにMV表記があり、グループと楽曲名が一意に特定でき、既存の曲名・動画IDと重複しないこと。ライブ・ダンス・メイキング・ティザー・別バージョンなどは除外
- 判別できないMV候補：Actionsのログに `REVIEW` として出力し、自動追加しない
- 一部の公式チャンネルの取得が両方式で失敗した場合：不完全な結果を公開せずワークフローを失敗させる
- 新規MVがない場合：コミットせず終了
- 新規MVがある場合：`data/music-gacha.json` と件数メタデータを更新して `main` にコミット
- YouTube APIキーは不要

**重要：** GitHub Actionsの `GITHUB_TOKEN` によるコミットでは、GitHub Pagesの再ビルドが起動されない。ガチャのJavaScriptは、その制限を避けるため、GitHub `main` の公開JSONを直接読み、失敗した場合だけPagesに同梱されたJSONへフォールバックする。HTMLやCSSのデザインは変更していない。

**注意：** 実際のYouTube動画欄の取得可否やGitHub Actionsの実行許可は環境に依存する。初回のワークフロー実行結果とページ表示は別途確認が必要。
