import os
import sys
import pytest
import warnings
import traceback
from _pytest.recwarn import WarningsRecorder

if sys.version_info >= (3, 8):
    from importlib import metadata as importlib_metadata
else:
    import importlib_metadata

counted_warnings = {}
warnings_recorder = WarningsRecorder()
default_formatwarning = warnings_recorder._module.formatwarning
default_showwarning = warnings_recorder._module.showwarning


def showwarning_with_traceback(message, category, filename, lineno, file=None, line=None):
    msg = warnings.WarningMessage(message, category, filename, lineno, file, line)

    msg.formatted_traceback = traceback.format_stack()
    msg.traceback = traceback.extract_stack()

    if hasattr(warnings, "_showwarnmsg_impl"):
        warnings._showwarnmsg_impl(msg)
    else:  # python 2
        warnings._show_warning(message, category, filename, lineno, file, line)


def formatwarning_with_traceback(message, category, filename, lineno, line=None):
    """Function to format a warning the standard way."""
    msg = warnings.WarningMessage(message, category, filename, lineno, None, line)

    msg.formatted_traceback = traceback.format_stack()
    msg.traceback = traceback.extract_stack()

    if hasattr(warnings, "_formatwarnmsg_impl"):
        return warnings._formatwarnmsg_impl(msg)
    else:
        return warnings.default_formatwarning(message, category, filename, lineno, line)


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

    warnings_recorder._module.showwarning = showwarning_with_traceback
    warnings_recorder._module.formatwarning = formatwarning_with_traceback
    if not hasattr(warnings_recorder._module, "_formatwarnmsg_impl"):
        warnings_recorder._module.default_formatwarning = default_formatwarning

    yield

    warnings_recorder._module.formatwarning = default_formatwarning
    warnings_recorder._module.showwarning = default_showwarning
    if not hasattr(warnings_recorder._module, "_formatwarnmsg_impl"):
        del warnings_recorder._module.default_formatwarning

    warnings_recorder.__exit__(None, None, None)

    for warning in warnings_recorder.list:
        # this code is adapted from python official warnings module

        # Search the filters
        for filter in warnings.filters:
            action, msg, cat, mod, ln = filter

            module = warning.filename or "<unknown>"
            if module[-3:].lower() == ".py":
                module = module[:-3] # XXX What about leading pathname?

            if ((msg is None or msg.match(str(warning.message))) and
                issubclass(warning.category, cat) and
                (mod is None or mod.match(module)) and
                (ln == 0 or warning.lineno == ln)):
                break
        else:
            action = warnings.defaultaction

        # Early exit actions
        if action == "ignore":
            continue

        warning.item = item
        quadruplet = (warning.filename, warning.lineno, warning.category, str(warning.message))

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
            path = path[len(pwd) + 1:]
        if "/site-packages/" in path:  # tox install the package in general
            path = path.split("/site-packages/")[1]
        return path
        
    def format_test_function_location(item):
        return "%s::%s:%s" % (item.location[0], item.location[2], item.location[1])

    yield
    
    def output_file():
        if os.path.exists("/workspace"):
            return '/workspace/warnings.txt'
        else:
            return 'warnings.txt'

    if counted_warnings:
        print("")
        print("warnings summary:")
        print("============================")
        for warning in sorted(counted_warnings.values(), key=lambda x: (x.filename, x.lineno)):
            print("%s\n-> %s:%s %s('%s')" % (format_test_function_location(warning.item), cut_path(warning.filename), warning.lineno, warning.category.__name__, warning.message))

        print("")
        print(f"All Warning errors can be found in the {output_file()} file.")

        warnings_as_json = []

        for warning in counted_warnings.values():
            serialized_warning = {x: str(getattr(warning.message, x)) for x in dir(warning.message) if not x.startswith("__")}

            saved_traceback = warning.traceback[:]

            stack_item = warning.traceback[-1]
            while stack_item.filename != warning.filename and stack_item.lineno != warning.lineno:
                warning.traceback.pop()
                warning.formatted_traceback.pop()
                if warning.traceback:
                    stack_item = warning.traceback[-1]
                else:  # we failed to find the line from which the warning is coming
                    warning.traceback = saved_traceback
                    break

            serialized_traceback = []
            for x in warning.traceback:
                serialized_frame = {key: getattr(x, key) for key in dir(x) if not key.startswith("_")}
                if os.path.exists(serialized_frame["filename"]):
                    serialized_frame["file_content"] = open(serialized_frame["filename"]).read()
                else:
                    serialized_frame["file_content"] = None
                serialized_frame["filename"] = cut_path(serialized_frame["filename"])
                # d[serialized_frame.encode("ascii", "ignore").decode('utf-8')
                serialized_traceback.append(serialized_frame)

            serialized_warning.update({
                "path": cut_path(warning.filename),
                "lineno": warning.lineno,
                "count":1,
                "warning_message": str(warning.message),
            })

            # How we format the warnings
            #<filename/path>:<line number>:<character number> <warning message>

            if "with_traceback" in serialized_warning:
                del serialized_warning["with_traceback"]            
            warnings_as_json.append(serialized_warning)

        with open(output_file(), "w") as f:
            for i in warnings_as_json: 
                f.write( f'{i["path"]}:{i["lineno"]}:1:{i["warning_message"]}')
                f.write('\n')
    else:
        # nothing, clear file
        with open(output_file(), "w") as f:
            f.write("")
