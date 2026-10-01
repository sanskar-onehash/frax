def register_all_tools():
    from frax.tools import (
        app_tools,
        capabilities,
        context,
        core,
        customizations,
        documents,
        erpnext,
        scripting,
    )

    core.register()
    context.register()
    capabilities.register()
    app_tools.register()
    customizations.register()
    documents.register()
    scripting.register()
    erpnext.register()
