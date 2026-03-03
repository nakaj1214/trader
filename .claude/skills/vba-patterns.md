---
name: vba-patterns
description: VBA共通パターン - データ検索、ループ、ファイル操作、コレクションで頻出のユーティリティ。
---

# VBA共通パターン

よく使うVBAタスク向けの再利用可能パターンとユーティリティ。

## 使う場面

- 最終行/列の取得
- 範囲ループの高速化
- ファイル操作
- コレクション/ディクショナリ操作

## 最終行/列の取得

```vba
Function GetLastRow(ByVal ws As Worksheet, Optional ByVal columnNumber As Long = 1) As Long
    ' 指定列の最終行
    GetLastRow = ws.Cells(ws.Rows.Count, columnNumber).End(xlUp).Row
End Function

Function GetLastColumn(ByVal ws As Worksheet, Optional ByVal rowNumber As Long = 1) As Long
    ' 指定行の最終列
    GetLastColumn = ws.Cells(rowNumber, ws.Columns.Count).End(xlToLeft).Column
End Function
```

## 範囲を効率的にループ

```vba
Sub ProcessRangeEfficiently()
    Dim ws As Worksheet
    Dim dataRange As Range
    Dim dataArray As Variant
    Dim i As Long

    Set ws = ThisWorkbook.Sheets("Data")
    Set dataRange = ws.Range("A1:C" & GetLastRow(ws, 1))

    ' 範囲を配列に読み込み（高速）
    dataArray = dataRange.Value

    ' 配列を処理（セル単位より高速）
    For i = LBound(dataArray, 1) To UBound(dataArray, 1)
        ' dataArray(i, 1), dataArray(i, 2) などを処理
    Next i

    ' 変更があれば書き戻し
    dataRange.Value = dataArray
End Sub
```

## ユーザー入力の検証

```vba
Function ValidateEmail(ByVal email As String) As Boolean
    Dim regex As Object
    Set regex = CreateObject("VBScript.RegExp")

    With regex
        .Pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        .IgnoreCase = True
        ValidateEmail = .Test(email)
    End With
End Function

Function IsNumericInput(ByVal input As String) As Boolean
    IsNumericInput = IsNumeric(input) And input <> ""
End Function
```

## ファイル操作

```vba
Function FileExists(ByVal filePath As String) As Boolean
    FileExists = (Dir(filePath) <> "")
End Function

Function GetFileName() As String
    ' ファイル選択ダイアログ
    Dim fd As FileDialog
    Set fd = Application.FileDialog(msoFileDialogFilePicker)

    With fd
        .Title = "Select a file"
        .Filters.Clear
        .Filters.Add "Excel Files", "*.xlsx;*.xlsm"
        .Filters.Add "All Files", "*.*"

        If .Show = -1 Then
            GetFileName = .SelectedItems(1)
        Else
            GetFileName = ""
        End If
    End With
End Function

Sub ReadTextFile(ByVal filePath As String)
    Dim fileNum As Integer
    Dim lineText As String

    fileNum = FreeFile

    Open filePath For Input As #fileNum

    Do While Not EOF(fileNum)
        Line Input #fileNum, lineText
        ' 行データ処理
        Debug.Print lineText
    Loop

    Close #fileNum
End Sub
```

## コレクションとディクショナリ

### Dictionary（キー・バリュー）

```vba
Sub UseDictionary()
    Dim dict As Object
    Set dict = CreateObject("Scripting.Dictionary")

    ' 追加
    dict.Add "Key1", "Value1"
    dict.Add "Key2", "Value2"

    ' キー存在確認
    If dict.Exists("Key1") Then
        Debug.Print dict("Key1")
    End If

    ' ループ
    Dim key As Variant
    For Each key In dict.Keys
        Debug.Print key & ": " & dict(key)
    Next key
End Sub
```

### Collection

```vba
Sub UseCollection()
    Dim coll As Collection
    Set coll = New Collection

    ' 追加
    coll.Add "Item1"
    coll.Add "Item2", "UniqueKey"

    ' インデックス/キーで取得
    Debug.Print coll(1)  ' 最初のアイテム
    Debug.Print coll("UniqueKey")

    ' ループ
    Dim item As Variant
    For Each item In coll
        Debug.Print item
    Next item
End Sub
```

## パフォーマンス最適化

### 画面更新を無効化

```vba
Sub OptimizedDataProcessing()
    ' 画面更新をオフ
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual
    Application.EnableEvents = False

    On Error GoTo Cleanup

    ' 処理ロジック
    ' ... バルク処理 ...

Cleanup:
    ' 設定を必ず戻す
    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic
    Application.EnableEvents = True

    If Err.Number <> 0 Then
        MsgBox "Error: " & Err.Description
    End If
End Sub
```

### Select/Activateを避ける

```vba
' Bad: 遅くて壊れやすい
Sub BadExample()
    Sheets("Data").Select
    Range("A1").Select
    Selection.Value = "Hello"
End Sub

' Good: 直接参照
Sub GoodExample()
    Sheets("Data").Range("A1").Value = "Hello"
End Sub

' Better: オブジェクト変数を使う
Sub BestExample()
    Dim dataSheet As Worksheet
    Set dataSheet = Sheets("Data")
    dataSheet.Range("A1").Value = "Hello"
End Sub
```

### バルク操作は配列で

```vba
' 遅い: セル単位
Sub SlowMethod()
    Dim i As Long
    For i = 1 To 10000
        Cells(i, 1).Value = i
    Next i
End Sub

' 速い: 配列ベース
Sub FastMethod()
    Dim data() As Variant
    Dim i As Long

    ReDim data(1 To 10000, 1 To 1)
    For i = 1 To 10000
        data(i, 1) = i
    Next i

    Range("A1:A10000").Value = data
End Sub
```

## VBAコードのテスト

### デバッグテクニック

```vba
Sub DebugExample()
    Dim value As Long
    value = 10

    ' イミディエイトウィンドウへ出力（Ctrl+G）
    Debug.Print "Value is: " & value

    ' アサーション
    Debug.Assert value > 0  ' falseなら停止

    ' ブレークポイント: 左余白クリック or F9
    ' ステップ実行: F8
    ' ウォッチ: 監視したい変数を追加
End Sub
```

### ユニットテストパターン

```vba
Sub TestCalculateTax()
    Dim result As Double

    ' テストケース1: 通常入力
    result = CalculateTax(100)
    Debug.Assert result = 20  ' 税率20%を想定

    ' テストケース2: ゼロ入力
    result = CalculateTax(0)
    Debug.Assert result = 0

    ' テストケース3: 負の入力（エラー想定）
    On Error Resume Next
    result = CalculateTax(-100)
    Debug.Assert Err.Number <> 0
    On Error GoTo 0

    Debug.Print "All tests passed!"
End Sub
```

## 関連スキル

- [vba-core](vba-core.md): VBAコアベストプラクティス
- [vba-excel](vba-excel.md): Excel固有パターン
- [tdd-workflow](tdd-workflow.md): テスト駆動開発
