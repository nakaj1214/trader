---
name: vba-excel
description: Excel固有のVBAパターン - ワークシート/ブックイベント、UserForms、Excel自動化。
---

# Excel固有のVBAパターン

Excel自動化、イベント、UserFormsに特化したパターン。

## 使う場面

- ワークシート変更の処理
- ブックイベントの自動化
- UserForm作成
- Excel固有の自動化タスク

## ワークシートイベント

```vba
' ワークシートモジュール内（例: Sheet1）
Private Sub Worksheet_Change(ByVal Target As Range)
    ' セル値の変更時に発火
    If Not Intersect(Target, Range("A1:A10")) Is Nothing Then
        ' A1:A10が変わった時の処理
    End If
End Sub

Private Sub Worksheet_SelectionChange(ByVal Target As Range)
    ' 選択変更時に発火
End Sub

Private Sub Worksheet_BeforeDoubleClick(ByVal Target As Range, Cancel As Boolean)
    ' ダブルクリック前に発火
    ' Cancel = True で既定動作を止める
End Sub

Private Sub Worksheet_Calculate()
    ' 再計算後に発火
End Sub
```

## ブックイベント

```vba
' ThisWorkbookモジュール内
Private Sub Workbook_Open()
    ' ブックを開いた時に実行
    MsgBox "Welcome!"
End Sub

Private Sub Workbook_BeforeSave(ByVal SaveAsUI As Boolean, Cancel As Boolean)
    ' 保存前に実行
    If Not ValidateData() Then
        Cancel = True
        MsgBox "保存前にエラーを修正してください"
    End If
End Sub

Private Sub Workbook_BeforeClose(Cancel As Boolean)
    ' 閉じる前に実行
    ' 後始末処理
End Sub

Private Sub Workbook_SheetActivate(ByVal Sh As Object)
    ' どのシートでもアクティブ時に実行
End Sub

Private Sub Workbook_NewSheet(ByVal Sh As Object)
    ' 新しいシート追加時に実行
End Sub
```

## UserForm ベストプラクティス

### フォーム初期化

```vba
' UserFormコード内
Private Sub UserForm_Initialize()
    ' 読み込み時の初期設定
    Me.ComboBox1.AddItem "Option 1"
    Me.ComboBox1.AddItem "Option 2"
    Me.ComboBox1.AddItem "Option 3"

    ' 既定値設定
    Me.TextBox1.Value = ""
    Me.ComboBox1.ListIndex = 0
End Sub
```

### ボタンクリック処理

```vba
Private Sub CommandButton1_Click()
    ' 入力検証
    If Trim(Me.TextBox1.Value) = "" Then
        MsgBox "Name is required", vbExclamation
        Me.TextBox1.SetFocus
        Exit Sub
    End If

    ' フォームデータ処理
    ProcessFormData

    ' フォームを閉じる
    Unload Me
End Sub

Private Sub CommandButton2_Click()
    ' キャンセルボタン
    Unload Me
End Sub
```

### フォームデータ処理

```vba
Private Sub ProcessFormData()
    Dim ws As Worksheet
    Dim lastRow As Long

    Set ws = ThisWorkbook.Sheets("Data")
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row + 1

    ' フォームデータをシートへ書き込み
    ws.Cells(lastRow, 1).Value = Me.TextBox1.Value
    ws.Cells(lastRow, 2).Value = Me.ComboBox1.Value
    ws.Cells(lastRow, 3).Value = Now()
End Sub
```

## VBAセキュリティ ベストプラクティス

### 入力サニタイズ

```vba
Function SanitizeInput(ByVal userInput As String) As String
    ' 危険な文字を除去
    SanitizeInput = Replace(userInput, "'", "''")  ' SQLインジェクション対策
    SanitizeInput = Replace(SanitizeInput, ";", "")
    SanitizeInput = Trim(SanitizeInput)
End Function
```

### SQLインジェクション回避

```vba
' Bad: SQLインジェクション脆弱性
Sub BadDatabaseQuery(ByVal userName As String)
    Dim sql As String
    sql = "SELECT * FROM Users WHERE Name = '" & userName & "'"
    ' Vulnerable to injection!
End Sub

' Good: ADODBのパラメータ化クエリを使う
Sub GoodDatabaseQuery(ByVal userName As String)
    Dim conn As Object
    Dim cmd As Object

    Set conn = CreateObject("ADODB.Connection")
    Set cmd = CreateObject("ADODB.Command")

    conn.Open "your_connection_string"

    With cmd
        .ActiveConnection = conn
        .CommandText = "SELECT * FROM Users WHERE Name = ?"
        .Parameters.Append .CreateParameter("@Name", 200, 1, 50, userName)
        .Execute
    End With
End Sub
```

### 機密データの保護

```vba
' 認証情報をハードコードしない
' Bad
Const DB_PASSWORD As String = "MyPassword123"

' Good: Windows Credential Managerや環境変数を使う
Function GetPassword() As String
    ' ユーザーに入力してもらうか安全な保管場所から取得
    GetPassword = InputBox("Enter password:", "Authentication")
End Function
```

## モダンプラットフォームへの移行

### VBA -> Office Scripts（Excel Online）

```typescript
// Office Scripts (TypeScript)
function main(workbook: ExcelScript.Workbook) {
  // VBAに近いがTypeScriptで記述
  let sheet = workbook.getActiveWorksheet();
  sheet.getRange("A1").setValue("Hello");
}
```

### VBA -> Python（openpyxl）

```python
# Python equivalent
from openpyxl import load_workbook

wb = load_workbook('file.xlsx')
ws = wb.active
ws['A1'] = 'Hello'
wb.save('file.xlsx')
```

## ツールとアドイン

- **Rubberduck VBA**: コード品質分析
- **VBA Code Cleaner**: コード整形とクリーニング
- **Excel-DNA**: .NETベースのExcelアドイン作成
- **Git for VBA**: バージョン管理連携

## 関連スキル

- [vba-core](vba-core.md): VBAコアベストプラクティス
- [vba-patterns](vba-patterns.md): 共通VBAパターン
- [systematic-debugging](systematic-debugging.md): VBAデバッグ
