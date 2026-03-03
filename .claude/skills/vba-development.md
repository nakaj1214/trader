---
name: vba-development
description: Excel/WordなどOfficeアプリ向けVBA開発ワークフロー。詳細は関連スキル参照。
---

# VBA開発スキル

Microsoft Officeアプリケーション向けVBAコードを開発・テスト・保守するための包括的ワークフロー。

## このスキルを使う場面

- Excelマクロやアドイン開発
- Word自動化スクリプト作成
- Accessデータベースアプリ構築
- Outlook自動化
- VBAデバッグ
- VBAパフォーマンス最適化

## クイックリファレンス

このスキルは以下のサブスキルに分割:

| スキル | 説明 |
|-------|-------------|
| [vba-core](vba-core.md) | コード整理、エラーハンドリング、変数宣言 |
| [vba-patterns](vba-patterns.md) | 共通ユーティリティ: データ検索、ループ、ファイル操作、コレクション |
| [vba-excel](vba-excel.md) | Excel固有: イベント、UserForms、セキュリティ |

## 必須ルール

### Option Explicitは必須

```vba
Option Explicit  ' 各モジュールの先頭
```

### エラーハンドリング必須

```vba
Public Function ProcessData() As Boolean
    On Error GoTo ErrorHandler

    ' Your code here
    ProcessData = True
    Exit Function

ErrorHandler:
    Debug.Print "Error: " & Err.Description
    ProcessData = False
End Function
```

### オブジェクトは必ず解放

```vba
Sub ProperCleanup()
    Dim wb As Workbook
    On Error GoTo Cleanup

    Set wb = Workbooks.Open("file.xlsx")
    ' Process...

Cleanup:
    If Not wb Is Nothing Then wb.Close False
    Set wb = Nothing
End Sub
```

### Select/Activateは避ける

```vba
' Bad
Sheets("Data").Select
Range("A1").Select
Selection.Value = "Hello"

' Good
Sheets("Data").Range("A1").Value = "Hello"
```

## パフォーマンスのコツ

1. **画面更新をオフ**（大量処理時）
2. **配列を使う**（セル単位操作を避ける）
3. **Select/Activateを使わない**
4. **オブジェクトを解放**してメモリリークを防ぐ

## 関連スキル

- [vba-core](vba-core.md): コアベストプラクティス
- [vba-patterns](vba-patterns.md): 共通パターンとユーティリティ
- [vba-excel](vba-excel.md): Excel固有パターン
- [code-review](code-review.md): VBAコード品質レビュー
- [systematic-debugging](systematic-debugging.md): VBAデバッグ
