Run python scripts/run_inflection_shadow.py
HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 2540.T"}}}
$2540.T: No data found, symbol may be delisted

1 Failed download:
['2540.T']: No data found, symbol may be delisted
HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 2540.T"}}}
$2540.T: No data found, symbol may be delisted

1 Failed download:
['2540.T']: No data found, symbol may be delisted
$2540.T: No data found, symbol may be delisted

1 Failed download:
['2540.T']: No data found, symbol may be delisted
$2686.T: No data found, symbol may be delisted

1 Failed download:
['2686.T']: No data found, symbol may be delisted
$2686.T: No data found, symbol may be delisted

1 Failed download:
['2686.T']: No data found, symbol may be delisted
$2686.T: No data found, symbol may be delisted

1 Failed download:
['2686.T']: No data found, symbol may be delisted
$3198.T: No data found, symbol may be delisted

1 Failed download:
['3198.T']: No data found, symbol may be delisted
$3198.T: No data found, symbol may be delisted

1 Failed download:
['3198.T']: No data found, symbol may be delisted
$3198.T: No data found, symbol may be delisted

1 Failed download:
['3198.T']: No data found, symbol may be delisted
$3546.T: No data found, symbol may be delisted

1 Failed download:
['3546.T']: No data found, symbol may be delisted
$3546.T: No data found, symbol may be delisted

1 Failed download:
['3546.T']: No data found, symbol may be delisted
$3546.T: No data found, symbol may be delisted

1 Failed download:
['3546.T']: No data found, symbol may be delisted
$3681.T: No data found, symbol may be delisted

1 Failed download:
['3681.T']: No data found, symbol may be delisted
$3681.T: No data found, symbol may be delisted

1 Failed download:
['3681.T']: No data found, symbol may be delisted
$3681.T: No data found, symbol may be delisted

1 Failed download:
['3681.T']: No data found, symbol may be delisted
$4449.T: No data found, symbol may be delisted

1 Failed download:
['4449.T']: No data found, symbol may be delisted
$4449.T: No data found, symbol may be delisted

1 Failed download:
['4449.T']: No data found, symbol may be delisted
$4449.T: No data found, symbol may be delisted

1 Failed download:
['4449.T']: No data found, symbol may be delisted
$4494.T: No data found, symbol may be delisted

1 Failed download:
['4494.T']: No data found, symbol may be delisted
$4494.T: No data found, symbol may be delisted

1 Failed download:
['4494.T']: No data found, symbol may be delisted
$4494.T: No data found, symbol may be delisted

1 Failed download:
['4494.T']: No data found, symbol may be delisted
$4659.T: No data found, symbol may be delisted

1 Failed download:
['4659.T']: No data found, symbol may be delisted
$4659.T: No data found, symbol may be delisted

1 Failed download:
['4659.T']: No data found, symbol may be delisted
$4659.T: No data found, symbol may be delisted

1 Failed download:
['4659.T']: No data found, symbol may be delisted
$5856.T: No data found, symbol may be delisted

1 Failed download:
['5856.T']: No data found, symbol may be delisted
$5856.T: No data found, symbol may be delisted

1 Failed download:
['5856.T']: No data found, symbol may be delisted
$5856.T: No data found, symbol may be delisted

1 Failed download:
['5856.T']: No data found, symbol may be delisted
$6403.T: No data found, symbol may be delisted

1 Failed download:
['6403.T']: No data found, symbol may be delisted
$6403.T: No data found, symbol may be delisted

1 Failed download:
['6403.T']: No data found, symbol may be delisted
$6403.T: No data found, symbol may be delisted

1 Failed download:
['6403.T']: No data found, symbol may be delisted
$7922.T: No data found, symbol may be delisted

1 Failed download:
['7922.T']: No data found, symbol may be delisted
$7922.T: No data found, symbol may be delisted

1 Failed download:
['7922.T']: No data found, symbol may be delisted
$7922.T: No data found, symbol may be delisted

1 Failed download:
['7922.T']: No data found, symbol may be delisted
$8289.T: No data found, symbol may be delisted

1 Failed download:
['8289.T']: No data found, symbol may be delisted
$8289.T: No data found, symbol may be delisted

1 Failed download:
['8289.T']: No data found, symbol may be delisted
$8289.T: No data found, symbol may be delisted

1 Failed download:
['8289.T']: No data found, symbol may be delisted
$9927.T: No data found, symbol may be delisted

1 Failed download:
['9927.T']: No data found, symbol may be delisted
$9927.T: No data found, symbol may be delisted

1 Failed download:
['9927.T']: No data found, symbol may be delisted
$9927.T: No data found, symbol may be delisted

1 Failed download:
['9927.T']: No data found, symbol may be delisted
Traceback (most recent call last):
  File "/home/runner/work/trader/trader/scripts/run_inflection_shadow.py", line 166, in <module>
    main()
  File "/home/runner/work/trader/trader/scripts/run_inflection_shadow.py", line 148, in main
    snapshot, snapshot_created = persist_report(report, encryption_secret=encryption_secret)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/trader/trader/scripts/run_inflection_shadow.py", line 118, in persist_report
    validate_report(report)
  File "/home/runner/work/trader/trader/scripts/run_inflection_shadow.py", line 55, in validate_report
    raise RuntimeError(
RuntimeError: DATA_HEALTH: latest market-date coverage too low: date=2026-09-09, 2855/3656 (78.1%)
Error: Process completed with exit code 1.
