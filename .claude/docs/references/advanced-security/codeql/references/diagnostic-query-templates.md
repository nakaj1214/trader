# 診断クエリテンプレート

CodeQL が認識するソースとシンクを列挙するための言語別 QL クエリ。[create-data-extensions ワークフロー](../workflows/create-data-extensions.md)で使用されます。

## ソース列挙クエリ

すべての言語で `RemoteFlowSource` クラスを使用します。インポートは言語ごとに異なります。

### インポートリファレンス

| 言語 | インポート | クラス |
|----------|---------|-------|
| Python | `import python` + `import semmle.python.dataflow.new.RemoteFlowSources` | `RemoteFlowSource` |
| JavaScript | `import javascript` | `RemoteFlowSource` |
| Java | `import java` + `import semmle.code.java.dataflow.FlowSources` | `RemoteFlowSource` |
| Go | `import go` | `RemoteFlowSource` |
| C/C++ | `import cpp` + `import semmle.code.cpp.security.FlowSources` | `RemoteFlowSource` |
| C# | `import csharp` + `import semmle.code.csharp.security.dataflow.flowsources.Remote` | `RemoteFlowSource` |
| Ruby | `import ruby` + `import codeql.ruby.dataflow.RemoteFlowSources` | `RemoteFlowSource` |

### テンプレート（Python — 上の表に従ってインポートを入れ替え）

```ql
/**
 * @name List recognized dataflow sources
 * @description Enumerates all locations CodeQL recognizes as dataflow sources
 * @kind problem
 * @id custom/list-sources
 */
import python
import semmle.python.dataflow.new.RemoteFlowSources

from RemoteFlowSource src
select src,
  src.getSourceType()
    + " | " + src.getLocation().getFile().getRelativePath()
    + ":" + src.getLocation().getStartLine().toString()
```

**注意:** `getSourceType()` は Python、Java、C# で利用可能です。Go、JavaScript、Ruby、C++ の場合は select を以下に置き換えてください:
```ql
select src,
  src.getLocation().getFile().getRelativePath()
    + ":" + src.getLocation().getStartLine().toString()
```

---

## シンク列挙クエリ

Concepts API は言語間で大きく異なります。正しいテンプレートを使用してください。

### コンセプトクラスリファレンス

| コンセプト | Python | JavaScript | Go | Ruby |
|---------|--------|------------|-----|------|
| SQL | `SqlExecution.getSql()` | `DatabaseAccess.getAQueryArgument()` | `SQL::QueryString`（Node の一種） | `SqlExecution.getSql()` |
| コマンド実行 | `SystemCommandExecution.getCommand()` | `SystemCommandExecution.getACommandArgument()` | `SystemCommandExecution.getCommandName()` | `SystemCommandExecution.getAnArgument()` |
| ファイルアクセス | `FileSystemAccess.getAPathArgument()` | `FileSystemAccess.getAPathArgument()` | `FileSystemAccess.getAPathArgument()` | `FileSystemAccess.getAPathArgument()` |
| HTTP クライアント | `Http::Client::Request.getAUrlPart()` | — | — | — |
| デコード | `Decoding.getAnInput()` | — | — | — |
| XML パース | — | — | — | `XmlParserCall.getAnInput()` |

### Python

```ql
/**
 * @name List recognized dataflow sinks
 * @description Enumerates security-relevant sinks CodeQL recognizes
 * @kind problem
 * @id custom/list-sinks
 */
import python
import semmle.python.Concepts

from DataFlow::Node sink, string kind
where
  exists(SqlExecution e | sink = e.getSql() and kind = "sql-execution")
  or
  exists(SystemCommandExecution e |
    sink = e.getCommand() and kind = "command-execution"
  )
  or
  exists(FileSystemAccess e |
    sink = e.getAPathArgument() and kind = "file-access"
  )
  or
  exists(Http::Client::Request r |
    sink = r.getAUrlPart() and kind = "http-request"
  )
  or
  exists(Decoding d | sink = d.getAnInput() and kind = "decoding")
  or
  exists(CodeExecution e | sink = e.getCode() and kind = "code-execution")
select sink,
  kind
    + " | " + sink.getLocation().getFile().getRelativePath()
    + ":" + sink.getLocation().getStartLine().toString()
```

### JavaScript / TypeScript

```ql
/**
 * @name List recognized dataflow sinks
 * @description Enumerates security-relevant sinks CodeQL recognizes
 * @kind problem
 * @id custom/list-sinks-js
 */
import javascript

from DataFlow::Node sink, string kind
where
  exists(DatabaseAccess e |
    sink = e.getAQueryArgument() and kind = "database-access"
  )
  or
  exists(SystemCommandExecution e |
    sink = e.getACommandArgument() and kind = "command-execution"
  )
  or
  exists(FileSystemAccess e |
    sink = e.getAPathArgument() and kind = "file-access"
  )
select sink,
  kind
    + " | " + sink.getLocation().getFile().getRelativePath()
    + ":" + sink.getLocation().getStartLine().toString()
```

### Go

```ql
/**
 * @name List recognized dataflow sinks
 * @description Enumerates security-relevant sinks CodeQL recognizes
 * @kind problem
 * @id custom/list-sinks-go
 */
import go
import semmle.go.frameworks.SQL

from DataFlow::Node sink, string kind
where
  sink instanceof SQL::QueryString and kind = "sql-query"
  or
  exists(SystemCommandExecution e |
    sink = e.getCommandName() and kind = "command-execution"
  )
  or
  exists(FileSystemAccess e |
    sink = e.getAPathArgument() and kind = "file-access"
  )
select sink,
  kind
    + " | " + sink.getLocation().getFile().getRelativePath()
    + ":" + sink.getLocation().getStartLine().toString()
```

### Ruby

```ql
/**
 * @name List recognized dataflow sinks
 * @description Enumerates security-relevant sinks CodeQL recognizes
 * @kind problem
 * @id custom/list-sinks-ruby
 */
import ruby
import codeql.ruby.Concepts

from DataFlow::Node sink, string kind
where
  exists(SqlExecution e | sink = e.getSql() and kind = "sql-execution")
  or
  exists(SystemCommandExecution e |
    sink = e.getAnArgument() and kind = "command-execution"
  )
  or
  exists(FileSystemAccess e |
    sink = e.getAPathArgument() and kind = "file-access"
  )
  or
  exists(CodeExecution e | sink = e.getCode() and kind = "code-execution")
select sink,
  kind
    + " | " + sink.getLocation().getFile().getRelativePath()
    + ":" + sink.getLocation().getStartLine().toString()
```

### Java

Java には統一された Concepts モジュールがありません。言語固有のシンククラスを使用します。診断クエリには `codeql/java-all` 依存関係を持つ独自の `qlpack.yml` が必要です — `.ql` ファイルと一緒に作成してください:

```yaml
# $DIAG_DIR/qlpack.yml
name: custom/diagnostics
version: 0.0.1
dependencies:
  codeql/java-all: "*"
```

クエリを実行する前に、診断ディレクトリで `codeql pack install` を実行してください。

```ql
/**
 * @name List recognized dataflow sinks
 * @description Enumerates security-relevant sinks CodeQL recognizes
 * @kind problem
 * @id custom/list-sinks
 */
import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.security.QueryInjection
import semmle.code.java.security.CommandLineQuery
import semmle.code.java.security.TaintedPathQuery
import semmle.code.java.security.XSS
import semmle.code.java.security.RequestForgery
import semmle.code.java.security.Xxe

from DataFlow::Node sink, string kind
where
  sink instanceof QueryInjectionSink and kind = "sql-injection"
  or
  sink instanceof CommandInjectionSink and kind = "command-injection"
  or
  sink instanceof TaintedPathSink and kind = "path-injection"
  or
  sink instanceof XssSink and kind = "xss"
  or
  sink instanceof RequestForgerySink and kind = "ssrf"
  or
  sink instanceof XxeSink and kind = "xxe"
select sink,
  kind
    + " | " + sink.getLocation().getFile().getRelativePath()
    + ":" + sink.getLocation().getStartLine().toString()
```

### C / C++

C++ も脆弱性クラス別の同様のパターンを使用します。`codeql/cpp-all` 依存関係を持つ `qlpack.yml` が必要です（Java と同じアプローチ）:

```yaml
# $DIAG_DIR/qlpack.yml
name: custom/diagnostics
version: 0.0.1
dependencies:
  codeql/cpp-all: "*"
```

クエリを実行する前に、診断ディレクトリで `codeql pack install` を実行してください。

```ql
/**
 * @name List recognized dataflow sinks
 * @description Enumerates security-relevant sinks CodeQL recognizes
 * @kind problem
 * @id custom/list-sinks-cpp
 */
import cpp
import semmle.code.cpp.dataflow.DataFlow
import semmle.code.cpp.security.CommandExecution
import semmle.code.cpp.security.FileAccess
import semmle.code.cpp.security.BufferWrite

from DataFlow::Node sink, string kind
where
  exists(FunctionCall call |
    sink.asExpr() = call.getAnArgument() and
    call.getTarget().hasGlobalOrStdName("system") and
    kind = "command-injection"
  )
  or
  exists(FunctionCall call |
    sink.asExpr() = call.getAnArgument() and
    call.getTarget().hasGlobalOrStdName(["fopen", "open", "freopen"]) and
    kind = "file-access"
  )
  or
  exists(FunctionCall call |
    sink.asExpr() = call.getAnArgument() and
    call.getTarget().hasGlobalOrStdName(["sprintf", "strcpy", "strcat", "gets"]) and
    kind = "buffer-write"
  )
  or
  exists(FunctionCall call |
    sink.asExpr() = call.getAnArgument() and
    call.getTarget().hasGlobalOrStdName(["execl", "execle", "execlp", "execv", "execvp", "execvpe", "popen"]) and
    kind = "command-execution"
  )
select sink,
  kind
    + " | " + sink.getLocation().getFile().getRelativePath()
    + ":" + sink.getLocation().getStartLine().toString()
```

### C\#

C# は脆弱性別のシンククラスを使用します。`codeql/csharp-all` 依存関係を持つ `qlpack.yml` が必要です:

```yaml
# $DIAG_DIR/qlpack.yml
name: custom/diagnostics
version: 0.0.1
dependencies:
  codeql/csharp-all: "*"
```

クエリを実行する前に、診断ディレクトリで `codeql pack install` を実行してください。

```ql
/**
 * @name List recognized dataflow sinks
 * @description Enumerates security-relevant sinks CodeQL recognizes
 * @kind problem
 * @id custom/list-sinks-csharp
 */
import csharp
import semmle.code.csharp.dataflow.DataFlow
import semmle.code.csharp.security.dataflow.SqlInjectionQuery
import semmle.code.csharp.security.dataflow.CommandInjectionQuery
import semmle.code.csharp.security.dataflow.TaintedPathQuery
import semmle.code.csharp.security.dataflow.XSSQuery

from DataFlow::Node sink, string kind
where
  sink instanceof SqlInjection::Sink and kind = "sql-injection"
  or
  sink instanceof CommandInjection::Sink and kind = "command-injection"
  or
  sink instanceof TaintedPath::Sink and kind = "path-injection"
  or
  sink instanceof XSS::Sink and kind = "xss"
select sink,
  kind
    + " | " + sink.getLocation().getFile().getRelativePath()
    + ":" + sink.getLocation().getStartLine().toString()
```
