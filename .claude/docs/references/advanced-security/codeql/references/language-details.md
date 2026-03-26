# 言語別ガイダンス

## ビルド不要

### Python

```bash
codeql database create codeql.db --language=python --source-root=.
```

**フレームワークサポート:**
- Django, Flask, FastAPI: 組み込みモデルあり
- Tornado, Pyramid: 部分的サポート
- カスタムフレームワーク: データ拡張が必要な場合あり

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| Django モデルが検出されない | `settings.py` が期待される場所にあることを確認 |
| 仮想環境が含まれる | 設定で `paths-ignore` を使用 |
| 型スタブが不足 | 抽出前に `types-*` パッケージをインストール |

### JavaScript/TypeScript

```bash
codeql database create codeql.db --language=javascript --source-root=.
```

**フレームワークサポート:**
- React, Vue, Angular: 組み込みモデルあり
- Express, Koa, Fastify: HTTP ソース/シンクモデルあり
- Next.js, Nuxt: 部分的 SSR サポート

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| node_modules の肥大化 | デフォルトで除外済み |
| TypeScript がパースされない | `tsconfig.json` が有効であることを確認 |
| モノレポの問題 | 特定のパッケージに `--source-root` を使用 |

### Go

```bash
codeql database create codeql.db --language=go --source-root=.
```

**フレームワークサポート:**
- net/http, Gin, Echo, Chi: 組み込みモデルあり
- gRPC: 部分的サポート
- カスタムルーター: データ拡張が必要な場合あり

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| 依存関係が不足 | 先に `go mod download` を実行 |
| vendor ディレクトリ | CodeQL が自動処理 |
| CGO コード | CGO を有効にして `--command='go build'` が必要 |

### Ruby

```bash
codeql database create codeql.db --language=ruby --source-root=.
```

**フレームワークサポート:**
- Rails: フルサポート（コントローラー、モデル、ビュー）
- Sinatra: 組み込みサポート
- Hanami: 部分的サポート

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| Bundler の問題 | 先に `bundle install` を実行 |
| Rails エンジン | 複数のデータベースパスが必要な場合あり |

## ビルド必要

### C/C++

```bash
# Make
codeql database create codeql.db --language=cpp --command='make -j8'

# CMake
codeql database create codeql.db --language=cpp \
  --source-root=/path/to/src \
  --command='cmake --build build'

# Ninja
codeql database create codeql.db --language=cpp \
  --command='ninja -C build'
```

**ビルドシステムのヒント:**
| ビルドシステム | コマンド |
|--------------|---------|
| Make | `make clean && make -j$(nproc)` |
| CMake | `cmake -B build && cmake --build build` |
| Meson | `meson setup build && ninja -C build` |
| Bazel | `bazel build //...` |

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| 部分的な抽出 | CodeQL ビルド前に `make clean` を確実に実行 |
| ヘッダーオンリーライブラリ | `--extractor-option cpp_trap_headers=true` を使用 |
| クロスコンパイル | `CODEQL_EXTRACTOR_CPP_TARGET_ARCH` を設定 |

### Java/Kotlin

```bash
# Gradle
codeql database create codeql.db --language=java --command='./gradlew build -x test'

# Maven
codeql database create codeql.db --language=java --command='mvn compile -DskipTests'
```

**フレームワークサポート:**
- Spring Boot: フルサポート
- Jakarta EE: 組み込みモデルあり
- Android: Android SDK が必要

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| 依存関係が不足 | 先に `./gradlew dependencies` を実行 |
| Kotlin 混在プロジェクト | `--language=java` を使用（両方をカバー） |
| アノテーションプロセッサ | CodeQL ビルド中に実行されることを確認 |

### Rust

```bash
codeql database create codeql.db --language=rust --command='cargo build'
```

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| proc マクロ | 特別な対応が必要な場合あり |
| ワークスペースプロジェクト | 特定のクレートに `--source-root` を使用 |
| ビルドスクリプトの失敗 | ネイティブ依存関係が利用可能であることを確認 |

### C#

```bash
# .NET Core
codeql database create codeql.db --language=csharp --command='dotnet build'

# MSBuild
codeql database create codeql.db --language=csharp --command='msbuild /t:rebuild'
```

**フレームワークサポート:**
- ASP.NET Core: フルサポート
- Entity Framework: データベースクエリモデルあり
- Blazor: 部分的サポート

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| NuGet の復元 | 先に `dotnet restore` を実行 |
| 複数のソリューション | コマンドでソリューションファイルを指定 |

### Swift

```bash
# Xcode プロジェクト
codeql database create codeql.db --language=swift \
  --command='xcodebuild -project MyApp.xcodeproj -scheme MyApp build'

# Swift Package Manager
codeql database create codeql.db --language=swift --command='swift build'
```

**要件:**
- macOS のみ
- Xcode Command Line Tools

**よくある問題:**
| 問題 | 修正方法 |
|-------|-----|
| コード署名 | `CODE_SIGN_IDENTITY=- CODE_SIGNING_REQUIRED=NO` を追加 |
| シミュレータターゲット | `-sdk iphonesimulator` を追加 |

## エクストラクタオプション

環境変数で設定: `CODEQL_EXTRACTOR_<LANG>_OPTION_<NAME>=<VALUE>`

### C/C++ オプション

| オプション | 説明 |
|--------|-------------|
| `trap_headers=true` | ヘッダーファイルの解析を含める |
| `target_arch=x86_64` | ターゲットアーキテクチャ |

### Java オプション

| オプション | 説明 |
|--------|-------------|
| `jdk_version=17` | 解析用の JDK バージョン |

### Python オプション

| オプション | 説明 |
|--------|-------------|
| `python_executable=/path/to/python` | 特定の Python インタープリタ |
