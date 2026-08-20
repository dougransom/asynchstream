try:
    import py_native_io
    py_native_io.patch_python_io()
except ImportError:
    pass