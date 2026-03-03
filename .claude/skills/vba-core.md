---
name: vba-core
description: VBAコアベストプラクティス - Officeアプリ向けのコード整理、エラーハンドリング、変数宣言。
---

# VBAコア ベストプラクティス

Microsoft Officeアプリケーションで保守しやすいVBAコードを書くための基本パターン。

## 使う場面

- 新規VBAプロジェクト開始時
- コーディング標準の策定
- VBAコード品質レビュー
- VBAベストプラクティスの教育

## コード整理

### モジュール構成

```vba
' ============================================================================
' Module: UserManagement
' Description: ユーザー関連の操作を担当
' Author: [Name]
' Date: [Date]
' ============================================================================

Option Explicit

' 公開定数
Public Const MODULE_VERSION As String = "1.0.0"

' モジュール内のプライベート変数
Private mUserList As Collection

' ============================================================================
' Public Functions
' ============================================================================

Public Function GetUser(ByVal userId As Long) As User
    ' Function implementation
End Function

' ============================================================================
' Private Helper Functions
' ============================================================================

Private Sub ValidateUserId(ByVal userId As Long)
    ' Validation logic
End Sub
```

## エラーハンドリング

### エラーハンドリングは必ず入れる

```vba
Public Function ProcessData(ByVal dataRange As Range) As Boolean
    On Error GoTo ErrorHandler

    ' 処理ロジック
    ProcessData = True
    Exit Function

ErrorHandler:
    ' エラー詳細をログ
    Debug.Print "Error in ProcessData: " & Err.Number & " - " & Err.Description

    ' 任意: ユーザー向けメッセージ
    MsgBox "データ処理中にエラーが発生しました。サポートに連絡してください。", _
           vbCritical, "Error"

    ProcessData = False
End Function
```

### 正しいエラーハンドリングパターン

```vba
Public Sub ImportData()
    On Error GoTo ErrorHandler

    Dim wb As Workbook
    Dim filePath As String

    ' ファイルパス取得
    filePath = Application.GetOpenFilename("Excel Files (*.xlsx), *.xlsx")
    If filePath = "False" Then Exit Sub

    ' ブックを開く
    Set wb = Workbooks.Open(filePath)

    ' データ処理
    ' ... ロジック ...

    ' クリーンアップ
    wb.Close SaveChanges:=False
    Set wb = Nothing

    Exit Sub

ErrorHandler:
    ' エラー時もリソースを解放
    If Not wb Is Nothing Then
        wb.Close SaveChanges:=False
        Set wb = Nothing
    End If

    MsgBox "Error: " & Err.Description, vbCritical
End Sub
```

## 変数宣言

### Option Explicitを必ず使う

```vba
Option Explicit  ' 各モジュールの先頭

' 良い例: 明示的な型
Dim userName As String
Dim userAge As Long
Dim salary As Double
Dim isActive As Boolean
Dim userSheet As Worksheet

' 悪い例: Variant（遅く、ミスしやすい）
Dim data  ' Variantになる
```

### 意味のある命名

```vba
' 良い例
Dim customerName As String
Dim totalRevenue As Double
Dim lastRow As Long

' 悪い例
Dim cn As String
Dim tr As Double
Dim lr As Long
```

## メモリ管理

### オブジェクトの解放を徹底

```vba
Sub ProperCleanup()
    Dim wb As Workbook
    Dim ws As Worksheet
    Dim rng As Range

    On Error GoTo ErrorHandler

    Set wb = Workbooks.Open("C:\data.xlsx")
    Set ws = wb.Sheets(1)
    Set rng = ws.Range("A1:Z1000")

    ' データ処理
    ' ...

    ' クリーンアップ
Cleanup:
    Set rng = Nothing
    Set ws = Nothing
    If Not wb Is Nothing Then wb.Close False
    Set wb = Nothing
    Exit Sub

ErrorHandler:
    Resume Cleanup
End Sub
```

## よくある落とし穴

1. **暗黙のVariant変換**: 変数型は明示する
2. **0始まり/1始まり**: VBA配列は両方、Rangeは1始まり
3. **ByRef/ByVal**: デフォルトはByRef。明示する
4. **Object/Primitive**: オブジェクトは`Set`、プリミティブは不要
5. **早期/遅延バインディング**: 早期は高速、遅延は柔軟

## ドキュメントテンプレート

```vba
'==============================================================================
' Function: CalculateTax
' Purpose: 所得に基づく税額を計算
' Parameters:
'   income (Double) - 総所得
'   taxRate (Double) - 税率（例: 0.20 = 20%）
' Returns: Double - 計算された税額
' Example: result = CalculateTax(50000, 0.20)  ' Returns 10000
' Author: [Name]
' Date: [Date]
' Modified: [Date] - [変更内容]
'==============================================================================
Public Function CalculateTax(ByVal income As Double, ByVal taxRate As Double) As Double
    On Error GoTo ErrorHandler

    ' 入力チェック
    If income < 0 Then
        Err.Raise vbObjectError + 1, , "Income cannot be negative"
    End If

    If taxRate < 0 Or taxRate > 1 Then
        Err.Raise vbObjectError + 2, , "Tax rate must be between 0 and 1"
    End If

    ' 税額計算
    CalculateTax = income * taxRate

    Exit Function

ErrorHandler:
    MsgBox "Error in CalculateTax: " & Err.Description, vbCritical
    CalculateTax = 0
End Function
```

## 関連スキル

- [vba-patterns](vba-patterns.md): VBA共通パターンとユーティリティ
- [vba-excel](vba-excel.md): Excel固有のパターン
- [code-review](code-review.md): コード品質レビュー
