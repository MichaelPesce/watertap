"""
Interface for flowsheet in :module:`metab`.
"""
from watertap.ui.api import FlowsheetInterface, BlockInterface
from watertap.examples.flowsheets.case_studies.wastewater_resource_recovery.metab import (
    metab,
)


def flowsheet_for_ui():
    model = metab.build()
    return FlowsheetInterface(
        model.fs, {"display_name": "METAB treatment train", "variables": []}
    )


if __name__ == "__main__":
    import json

    fsi = flowsheet_for_ui()
    print("Flowsheet data")
    print("--------------")
    print(json.dumps(fsi.as_dict(), indent=2))
