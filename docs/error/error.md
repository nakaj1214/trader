Deploy Dashboard v2
Run npm install
npm error code ENOENT
npm error syscall open
npm error path /home/runner/work/trader/trader/dashboard-v2/package.json
npm error errno -2
npm error enoent Could not read package.json: Error: ENOENT: no such file or directory, open '/home/runner/work/trader/trader/dashboard-v2/package.json'
npm error enoent This is related to npm not being able to find a file.
npm error enoent
npm error A complete log of this run can be found in: /home/runner/.npm/_logs/2026-03-07T12_09_40_132Z-debug-0.log
Error: Process completed with exit code 254.


Weekly Stock Analysis v2
Run python -m pip install --upgrade pip
Requirement already satisfied: pip in /opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages (26.0.1)
Obtaining file:///home/runner/work/trader/trader
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Checking if build backend supports build_editable: started
  Checking if build backend supports build_editable: finished with status 'done'
ERROR: Exception:
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/cli/base_command.py", line 107, in _run_wrapper
    status = _inner_run()
             ^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/cli/base_command.py", line 98, in _inner_run
    return self.run(options, args)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/cli/req_command.py", line 96, in wrapper
    return func(self, options, args)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/commands/install.py", line 392, in run
    requirement_set = resolver.resolve(
                      ^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/resolver.py", line 79, in resolve
    collected = self.factory.collect_root_requirements(root_reqs)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/factory.py", line 538, in collect_root_requirements
    reqs = list(
           ^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/factory.py", line 494, in _make_requirements_from_install_req
    cand = self._make_base_candidate_from_link(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/factory.py", line 205, in _make_base_candidate_from_link
    self._editable_candidate_cache[link] = EditableCandidate(
                                           ^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 343, in __init__
    super().__init__(
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 161, in __init__
    self.dist = self._prepare()
                ^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 238, in _prepare
    dist = self._prepare_distribution()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 353, in _prepare_distribution
    return self._factory.preparer.prepare_editable_requirement(self._ireq)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/operations/prepare.py", line 713, in prepare_editable_requirement
    dist = _get_prepared_distribution(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/operations/prepare.py", line 77, in _get_prepared_distribution
    abstract_dist.prepare_distribution_metadata(
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/distributions/sdist.py", line 53, in prepare_distribution_metadata
    self.req.editable_sanity_check()
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/req/req_install.py", line 501, in editable_sanity_check
    if self.editable and not self.supports_pyproject_editable:
                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/functools.py", line 1001, in __get__
    val = self.func(instance)
          ^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_internal/req/req_install.py", line 237, in supports_pyproject_editable
    return "build_editable" in self.pep517_backend._supported_features()
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_vendor/pyproject_hooks/_impl.py", line 180, in _supported_features
    return self._call_hook("_supported_features", ***)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.14/x64/lib/python3.11/site-packages/pip/_vendor/pyproject_hooks/_impl.py", line 402, in _call_hook
    raise BackendUnavailable(
pip._vendor.pyproject_hooks._impl.BackendUnavailable: Cannot import 'setuptools.backends._legacy'
Error: Process completed with exit code 2.