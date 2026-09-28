"""Collect the Tcl/Tk pair actually loaded by the build interpreter, not PATH."""
from PyInstaller import isolated


@isolated.decorate
def loaded_tk_runtime():
    import ctypes
    from pathlib import Path
    import tkinter
    from tkinter import ttk

    window = tkinter.Tk()
    window.withdraw()
    try:
        ttk.Progressbar(window).pack()
        window.update_idletasks()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
        kernel.GetModuleFileNameW.restype = ctypes.c_uint
        libraries = {}
        for package in ("Tcl", "Tk"):
            version = window.tk.call("package", "present", package)
            major_minor = "".join(version.split(".")[:2])
            for suffix in ("t.dll", ".dll"):
                name = package.lower() + major_minor + suffix
                handle = kernel.GetModuleHandleW(name)
                if not handle:
                    continue
                buffer = ctypes.create_unicode_buffer(32768)
                if not kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
                    raise ctypes.WinError(ctypes.get_last_error())
                path = Path(buffer.value)
                assert path.is_file()
                libraries[name] = str(path)
                break
            else:
                raise RuntimeError(f"Cannot locate the loaded {package} {version} DLL")
        return {
            "libraries": libraries,
            "tcl_data": window.tk.eval("info library"),
            "tk_data": window.tk.eval("set tk_library"),
            "tcl_version": window.tk.call("package", "present", "Tcl"),
            "tk_version": window.tk.call("package", "present", "Tk"),
        }
    finally:
        window.destroy()
