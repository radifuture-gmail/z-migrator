# 📊 Portfolio Migration Analyzer (Z-Score)

ポートフォリオの移行タイミングを統計的に判定するためのStreamlitアプリケーションです。

## 🌟 特徴
- **Base64解析**: URLパラメータや入力フォームからポートフォリオ構成（資産、比率）を即座に読み込み。
- **Z-Score判定**: 2つのポートフォリオ指数の対数比率から、現在の価格乖離を算出し、移行の是非を判定。
- **動的チャート**: Plotlyを使用したインタラクティブな価格指数比較とZスコア推移の可視化。

## 🛠 インストールと実行
1. リポジトリをクローン:
   ```bash
   git clone [https://github.com/あなたのユーザー名/portfolio-migrator.git](https://github.com/あなたのユーザー名/portfolio-migrator.git)