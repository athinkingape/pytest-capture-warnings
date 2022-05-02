import os
import sys
import pytest
import warnings
from _pytest.recwarn import WarningsRecorder

if sys.version_info >= (3, 8):
    from importlib import metadata as importlib_metadata  # noqa: F401
else:
    import importlib_metadata  # noqa: F401

counted_warnings = {}
warnings_recorder = WarningsRecorder()
default_formatwarning = warnings_recorder._module.formatwarning
default_showwarning = warnings_recorder._module.showwarning


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """
    Needed to grab the item.location information
    """
    global warnings_recorder

    if os.environ.get("PYTHONWARNINGS") == "ignore":
        yield
        return

    warnings_recorder.__enter__()
    yield
    warnings_recorder.__exit__(None, None, None)

    for warning in warnings_recorder.list:
        # this code is adapted from python official warnings module

        # Search the filters
        for filter in warnings.filters:
            action, msg, cat, mod, ln = filter

            module = warning.filename or "<unknown>"
            if module[-3:].lower() == ".py":
                module = module[:-3]  # XXX What about leading pathname?

            if (
                (msg is None or msg.match(str(warning.message)))
                and issubclass(warning.category, cat)
                and (mod is None or mod.match(module))
                and (ln == 0 or warning.lineno == ln)
            ):
                break
        else:
            action = warnings.defaultaction

        # Early exit actions
        if action == "ignore":
            continue

        warning.item = item
        quadruplet = (
            warning.filename,
            warning.lineno,
            warning.category,
            str(warning.message),
        )

        if quadruplet in counted_warnings:
            counted_warnings[quadruplet].count += 1
            continue
        else:
            warning.count = 1
            counted_warnings[quadruplet] = warning


@pytest.hookimpl(hookwrapper=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config=None):

    pwd = os.path.realpath(os.curdir)

    def cut_path(path):
        if path.startswith(pwd):
            path = path[len(pwd) + 1 :]  # noqa: E203
        if "/site-packages/" in path:
            path = path.split("/site-packages/")[1]
        return path

    def format_test_function_location(item):
        return "%s::%s:%s" % (item.location[0], item.location[2], item.location[1])

    yield

    if counted_warnings:
        print("")
        print("warnings summary:")
        print("============================")
        for warning in sorted(
            counted_warnings.values(), key=lambda x: (x.filename, x.lineno)
        ):
            print(
                "%s\n-> %s:%s %s('%s')"
                % (
                    format_test_function_location(warning.item),
                    cut_path(warning.filename),
                    warning.lineno,
                    warning.category.__name__,
                    warning.message,
                )
            )

        print("")
        print(f"All Warning errors can be found in the {output_path} file.")

        warnings_as_json = []

        for warning in counted_warnings.values():
            serialized_warning = {
                x: str(getattr(warning.message, x))
                for x in dir(warning.message)
                if not x.startswith("__")
            }

            serialized_warning.update(
                {
                    "path": cut_path(warning.filename),
                    "lineno": warning.lineno,
                    "count": 1,
                    "warning_message": str(warning.message),
                }
            )

            # How we format the warnings: pylint parseable format
            # {path}:{line}: [{msg_id}({symbol}), {obj}] {msg}
            # Always:
            # {path}:{line}: [W0513(warning), ] {msg}

            if "with_traceback" in serialized_warning:
                del serialized_warning["with_traceback"]
            warnings_as_json.append(serialized_warning)

        with open(output_path, "w") as f:
            for i in warnings_as_json:
                f.write(f'{i["path"]}:{i["lineno"]}: [W0513(warning), ] {i["warning_message"]}')
                f.write("\n")
    else:
        # nothing, clear file
        with open(output_path, "w") as f:
            pass


DEFAULT_OUTPUT = "warnings.txt"
def pytest_addoption(parser):
    parser.addoption(
        "--output",
        action="store",
        dest="outputpath",
        default=DEFAULT_OUTPUT,
    )


output_path = None


def pytest_configure(config):
    global output_path
    output_path = config.getoption("outputpath")
    if 'CAPTURE_WARNINGS_OUTPUT' in os.environ and output_path == DEFAULT_OUTPUT:
        output_path = os.environ['CAPTURE_WARNINGS_OUTPUT']
