Run python scripts/run_position_monitor.py
  python scripts/run_position_monitor.py
  shell: /usr/bin/bash -e {0}
  env:
    GOOGLE_SERVICE_ACCOUNT_JSON: 
    GOOGLE_SHEET_ID: 
    SLACK_WEBHOOK_URL: ***
    pythonLocation: /opt/hostedtoolcache/Python/3.11.16/x64
    PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.11.16/x64/lib/pkgconfig
    Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.11.16/x64
    Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.11.16/x64
    Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.11.16/x64
    LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.11.16/x64/lib
Traceback (most recent call last):
  File "/home/runner/work/trader/trader/scripts/run_position_monitor.py", line 187, in <module>
    raise SystemExit(main())
                     ^^^^^^
  File "/home/runner/work/trader/trader/scripts/run_position_monitor.py", line 183, in main
    return run(dry_run=args.dry_run)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/trader/trader/scripts/run_position_monitor.py", line 69, in run
    holdings = read_holdings()
               ^^^^^^^^^^^^^^^
  File "/home/runner/work/trader/trader/src/data/sheets_client.py", line 47, in read_holdings
    return list(_worksheet(worksheet_name).get_all_records())
                ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/trader/trader/src/data/sheets_client.py", line 35, in _worksheet
    raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID are required")
RuntimeError: GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID are required
Error: Process completed with exit code 1.