---
name: refactor-with-read-first
description: 同一ファイルへの Edit が5回を超えた場合に、ファイル全体を Read して設計を固めてから一括 Write するよう促す。細粒度 Edit の繰り返しによる手戻りを防止する。
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---
