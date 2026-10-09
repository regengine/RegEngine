"""Overlay writer must not own the global jurisdiction taxonomy.

Audit finding (low): ``OverlayWriter.create_jurisdiction_node`` wrote shared
``:Jurisdiction`` taxonomy nodes from a tenant-scoped writer with no callers,
violating layering. Jurisdiction hierarchy writes belong to
``services.graph.app.hierarchy_builder`` (global taxonomy, boot/migration
callers only). This test pins the removal: it fails while the dead writer
exists and passes once it is gone.
"""

import inspect


def test_overlay_writer_has_no_jurisdiction_writer():
    from services.graph.app import overlay_writer as overlay_writer_module

    assert not hasattr(overlay_writer_module.OverlayWriter, "create_jurisdiction_node"), (
        "OverlayWriter.create_jurisdiction_node is dead code that writes the "
        "global jurisdiction taxonomy from a tenant-scoped writer; it must stay "
        "deleted (canonical owner: hierarchy_builder.build_jurisdiction_hierarchy)"
    )


def test_overlay_writer_module_does_not_merge_jurisdiction_nodes():
    from services.graph.app import overlay_writer as overlay_writer_module

    source = inspect.getsource(overlay_writer_module)
    assert "MERGE (j:Jurisdiction" not in source, (
        "overlay_writer must not MERGE :Jurisdiction nodes; jurisdiction hierarchy writes belong to hierarchy_builder"
    )
    assert "shared.schemas import Jurisdiction" not in source, (
        "overlay_writer must not depend on the canonical Jurisdiction schema"
    )
