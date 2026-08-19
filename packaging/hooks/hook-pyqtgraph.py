"""Package only the PyQtGraph data used by WT-NameRelay.

The application does not use PyQtGraph's optional bundled color maps.  Keeping
them out of the executable avoids distributing unrelated CC BY/CC0 assets.
"""

from PyInstaller.utils.hooks import collect_data_files


datas = collect_data_files(
    "pyqtgraph",
    excludes=[
        "colors/maps/*",
        "examples/*",
    ],
)
